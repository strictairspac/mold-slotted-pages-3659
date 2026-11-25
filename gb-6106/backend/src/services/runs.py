import json
from time import time

from fastapi import HTTPException
from sqlalchemy import insert, select

from src.constants.job_state import JobState
from src.domain.scenario import CONFIG
from src.models.archives import run_archives, segments
from src.models.cases import cases
from src.models.runs import runs
from . import audit, cases as case_service


def query():
    """Run rows with their case title and archived payload, if any."""
    archived = (
        select(run_archives.c.run_id, segments.c.payload)
        .join(segments, segments.c.digest == run_archives.c.digest)
        .subquery()
    )
    return (
        select(runs, cases.c.title.label("case_title"), archived.c.payload.label("archived"))
        .join(cases, cases.c.id == runs.c.case_id)
        .outerjoin(archived, archived.c.run_id == runs.c.id)
    )


def list_query():
    """Summary rows: no archived payload, so listing stays light.

    Archived batches therefore report ``result`` as null in the list; the
    detail and export endpoints rehydrate the full result when needed.
    """
    return select(runs, cases.c.title.label("case_title")).join(cases, cases.c.id == runs.c.case_id)


def _entry(row):
    """Shape a row into a run dict, rehydrating an archived result.

    The result bytes are the canonical JSON of the original result, so a
    download made before archiving and one made after are byte-identical.
    """
    run = dict(row)
    archived = run.pop("archived", None)
    if run["result"] is None and archived is not None:
        run["result"] = json.loads(bytes(archived))
    return run


def get(db, run_id):
    row = db.execute(query().where(runs.c.id == run_id)).mappings().first()
    if row is None:
        raise HTTPException(404, "执行批次不存在")
    return _entry(row)


def list_entries(db):
    rows = db.execute(list_query().order_by(runs.c.id.desc()).limit(100)).mappings()
    return [_entry(row) for row in rows]


def enqueue(db, case_id, parameter, actor):
    if parameter > CONFIG["max_parameter"]:
        raise HTTPException(422, f"参数不能超过 {CONFIG['max_parameter']}")
    case_service.get(db, case_id)
    change = db.execute(insert(runs).values(
        case_id=case_id, status=JobState.QUEUED, parameter=parameter, actor=actor, created_at=int(time())
    ))
    run_id = change.inserted_primary_key[0]
    audit.record(db, "enqueue", actor, "run", run_id)
    return get(db, run_id)
