import json
from sqlalchemy import func, select

from migrations.v001_workbench import upgrade
from src.config.resources import engine
from src.config.settings import DEMO_PASSWORD
from src.constants.roles import Role
from src.domain.scenario import FIXTURES
from src.models.cases import cases
from src.models.users import users
from src.utils.dialect import insert_once
from src.utils.passwords import hash_password


def setup_schema():
    with engine.begin() as db:
        upgrade(db)


def seed():
    with engine.begin() as db:
        existing = set(db.execute(select(users.c.username)).scalars())
        for role in Role:
            if role.value not in existing:
                insert_once(db, users, {
                    "username": role.value, "role": role.value, "password_hash": hash_password(DEMO_PASSWORD),
                }, "username")
        for fixture in FIXTURES:
            insert_once(db, cases, {**fixture, "created_by": "seed"}, "code")
        return {table.name: db.scalar(select(func.count()).select_from(table)) for table in (users, cases)}


if __name__ == "__main__":
    setup_schema()
    print(json.dumps(seed(), sort_keys=True))
