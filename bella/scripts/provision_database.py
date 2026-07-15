"""Create Bella's isolated database in the shared Postgres instance."""

import os

import psycopg
from psycopg import sql

from bella.database import require_database_name

BELLA_DATABASE_NAME = "bella"
MAINTENANCE_DATABASE_NAME = "postgres"


def require_maintenance_database(admin_url: str) -> None:
    require_database_name(
        admin_url,
        MAINTENANCE_DATABASE_NAME,
        setting_name="POSTGRES_ADMIN_URL",
    )


def main() -> None:
    admin_url = os.environ["POSTGRES_ADMIN_URL"]
    require_maintenance_database(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (BELLA_DATABASE_NAME,),
        ).fetchone()
        if exists is None:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(BELLA_DATABASE_NAME)
                )
            )
            print("OK: created Bella's isolated database.")
        else:
            print("OK: Bella's isolated database already exists.")


if __name__ == "__main__":
    main()
