from fastapi import APIRouter, Depends, HTTPException, Response

from src.config.resources import engine
from src.controllers.access import identity, operator
from src.schemas.archives import ArchiveEntry, PurgeResult, SegmentEntry
from src.services import archives

router = APIRouter(tags=["Archive"])


@router.get("/segments", response_model=list[SegmentEntry], dependencies=[Depends(identity)])
def list_segments():
    with engine.connect() as db:
        return archives.list_segments(db)


@router.get("/runs/{run_id}/archive", response_model=ArchiveEntry, dependencies=[Depends(identity)])
def archive_detail(run_id: int):
    with engine.connect() as db:
        entry = archives.entry(db, run_id)
    if entry is None:
        raise HTTPException(404, "该批次尚未归档")
    return entry


@router.post("/runs/{run_id}/archive", response_model=ArchiveEntry, status_code=201)
def archive(run_id: int, user=Depends(operator)):
    return archives.archive(run_id, user["username"])


@router.get("/runs/{run_id}/archive/download", dependencies=[Depends(identity)])
def download(run_id: int):
    with engine.connect() as db:
        payload = archives.payload(db, run_id)
        entry = archives.entry(db, run_id)
    if entry is None:
        raise HTTPException(404, "该批次尚未归档")
    if payload is None:
        raise HTTPException(410, "归档地址段已不可用")
    return Response(payload, media_type="application/json", headers={
        "Content-Disposition": f"attachment; filename=segment-{entry['digest']}.json",
        "X-Segment-Digest": entry["digest"],
    })


@router.delete("/runs/{run_id}/archive", response_model=PurgeResult)
def purge(run_id: int, user=Depends(operator)):
    return archives.purge(run_id, user["username"])
