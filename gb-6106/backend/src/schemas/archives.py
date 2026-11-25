from pydantic import BaseModel


class ArchiveEntry(BaseModel):
    run_id: int
    digest: str
    archived_at: int
    size: int
    references: int


class SegmentEntry(BaseModel):
    digest: str
    size: int
    created_at: int
    references: int


class PurgeResult(BaseModel):
    run_id: int
    digest: str | None
    reclaimed: bool
