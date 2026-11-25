from sqlalchemy import BigInteger, Column, ForeignKey, Integer, LargeBinary, String, Table
from sqlalchemy.dialects.mysql import LONGBLOB

from .base import metadata


# One row per distinct completed-batch result ("追溯地址段"). The digest is the
# primary key, so batches with byte-identical results share a single stored
# copy no matter how often they are archived or how many of them reference it.
segments = Table(
    "segments", metadata,
    Column("digest", String(64), primary_key=True),
    Column("size", Integer, nullable=False),
    Column("payload", LargeBinary().with_variant(LONGBLOB, "mysql"), nullable=False),
    Column("created_at", BigInteger, nullable=False),
)

# One row per archived batch, holding that batch's own archive record and
# timestamp. Auditing is kept separately, so each batch retains its own history.
# The shared segment is reclaimed only after the last of these rows is removed.
run_archives = Table(
    "run_archives", metadata,
    Column("run_id", ForeignKey("runs.id"), primary_key=True),
    Column("digest", ForeignKey("segments.digest"), nullable=False, index=True),
    Column("archived_at", BigInteger, nullable=False),
)
