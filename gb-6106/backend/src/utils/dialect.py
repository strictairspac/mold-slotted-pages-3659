"""Dialect-aware "insert once, ignore duplicates".

Archive and queue tables use primary keys to absorb duplicate writes; this
keeps the behaviour identical on MySQL, SQLite and PostgreSQL.
"""
from sqlalchemy import insert
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


def insert_once(db, table, values, key):
    """Insert a row; a conflicting primary key leaves the existing row intact.

    Returns True only when a new row was actually written.
    """
    dialogue = db.dialect.name
    if dialogue == "mysql":
        statement = mysql_insert(table).values(**values).on_duplicate_key_update(
            **{key: table.c[key]}
        )
    elif dialogue == "postgresql":
        statement = pg_insert(table).values(**values).on_conflict_do_nothing(index_elements=[key])
    elif dialogue == "sqlite":
        statement = sqlite_insert(table).values(**values).on_conflict_do_nothing(index_elements=[key])
    else:
        statement = insert(table).values(**values)
    return db.execute(statement).rowcount == 1
