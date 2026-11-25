"""Archive completed batches into shared, content-addressed segments.

A segment is the canonical JSON of a completed batch's traceability result.
Its identity is the SHA-256 digest, so two batches whose address segments are
byte-identical share one stored copy while each keeps its own ``run_archives``
row and audit trail. The move runs in a single transaction: an interrupted
attempt leaves the batch untouched, and a retry finishes the job without ever
creating a second copy.

Lock order is always batch row, then segment row. That serialises two archives
(or a purge) touching the same batch, and an archive and a purge touching the
same segment, without a cycle.
"""
import json
from time import time

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update

from src.config.resources import engine
from src.constants.job_state import JobState
from src.models.archives import run_archives, segments
from src.models.runs import runs
from src.services import audit
from src.utils.dialect import insert_once
from src.utils.serial import canonical_json, content_digest


def _lock_batch(db, run_id):
    return db.execute(
        select(runs.c.status, runs.c.result).where(runs.c.id == run_id).with_for_update()
    ).mappings().first()


def _lock_segment(db, digest):
    return db.execute(
        select(segments.c.payload).where(segments.c.digest == digest).with_for_update()
    ).scalar()


def _linked(db, run_id):
    return db.scalar(select(run_archives.c.digest).where(run_archives.c.run_id == run_id))


def _references(db, digest):
    return db.scalar(
        select(func.count()).select_from(run_archives).where(run_archives.c.digest == digest)
    )


def _references_locked(db, digest):
    """Count references with a locking read so a stale snapshot cannot hide a
    link committed while this transaction waited for the segment lock."""
    rows = db.execute(
        select(run_archives.c.run_id).where(run_archives.c.digest == digest).with_for_update()
    ).scalars()
    return len(rows.all())


def entry(db, run_id):
    row = db.execute(select(run_archives).where(run_archives.c.run_id == run_id)).mappings().first()
    if row is None:
        return None
    record = dict(row)
    record["size"] = db.scalar(select(segments.c.size).where(segments.c.digest == record["digest"]))
    record["references"] = _references(db, record["digest"])
    return record


def payload(db, run_id):
    """Return the archived bytes for a batch, or None if it is not archived."""
    row = db.execute(
        select(segments.c.payload).join(run_archives, run_archives.c.digest == segments.c.digest)
        .where(run_archives.c.run_id == run_id)
    ).mappings().first()
    return bytes(row["payload"]) if row else None


def archive(run_id, actor):
    with engine.begin() as db:
        # Hold the batch row: a concurrent archive or purge of the same batch
        # waits here, and a plain read after taking the lock sees its commit.
        batch = _lock_batch(db, run_id)
        if batch is None:
            raise HTTPException(404, "执行批次不存在")
        if _linked(db, run_id) is not None:
            # Retry of a finished archive: a no-op that never adds a second copy.
            return entry(db, run_id)
        if batch["status"] != JobState.DONE or batch["result"] is None:
            raise HTTPException(409, "只有执行成功的批次可以归档")
        data = canonical_json(batch["result"])
        digest = content_digest(batch["result"])
        # Insert the shared segment (a duplicate PK is absorbed), then lock that
        # row so a purge cannot reclaim it between here and the link insert.
        insert_once(db, segments, {
            "digest": digest, "size": len(data), "payload": data, "created_at": int(time()),
        }, "digest")
        if _lock_segment(db, digest) is None:
            # A purge committed between the insert and the lock and removed the
            # row; put the shared copy back before linking this batch to it.
            insert_once(db, segments, {
                "digest": digest, "size": len(data), "payload": data, "created_at": int(time()),
            }, "digest")
            _lock_segment(db, digest)
        linked = insert_once(db, run_archives, {
            "run_id": run_id, "digest": digest, "archived_at": int(time()),
        }, "run_id")
        if linked:
            # The inline copy is no longer needed; reads rehydrate from the segment.
            db.execute(update(runs).where(runs.c.id == run_id).values(result=None))
            audit.record(db, "archive", actor, "run", run_id)
        return entry(db, run_id)


def purge(run_id, actor):
    """Remove one batch's archive link and reclaim its segment if unreferenced.

    A segment still referenced by another batch is left in place, so cleaning
    one batch never breaks the archived downloads of the rest. The cleaned
    batch keeps its own evidence: when it was the sole holder its result is
    restored from the segment before the shared copy is dropped.
    """
    with engine.begin() as db:
        batch = _lock_batch(db, run_id)
        if batch is None:
            raise HTTPException(404, "执行批次不存在")
        digest = _linked(db, run_id)
        if digest is None:
            return {"run_id": run_id, "digest": None, "reclaimed": False}
        stored = _lock_segment(db, digest)
        if stored is not None and batch["result"] is None:
            # Restore this batch's inline result so it stays downloadable.
            db.execute(update(runs).where(runs.c.id == run_id).values(result=json.loads(bytes(stored))))
        db.execute(delete(run_archives).where(run_archives.c.run_id == run_id))
        reclaimed = _references_locked(db, digest) == 0
        if reclaimed:
            db.execute(delete(segments).where(segments.c.digest == digest))
        audit.record(db, "purge", actor, "run", run_id)
    return {"run_id": run_id, "digest": digest, "reclaimed": reclaimed}


def list_segments(db):
    counts = (
        select(run_archives.c.digest, func.count().label("references"))
        .group_by(run_archives.c.digest).subquery()
    )
    statement = (
        select(segments.c.digest, segments.c.size, segments.c.created_at, counts.c.references)
        .join(counts, counts.c.digest == segments.c.digest)
        .order_by(segments.c.created_at.desc(), segments.c.digest)
    )
    return [dict(row) for row in db.execute(statement).mappings()]
