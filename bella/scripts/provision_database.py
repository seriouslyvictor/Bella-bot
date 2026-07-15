"""Create Bella's isolated database in the shared Postgres instance."""

import os

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

BELLA_DATABASE_NAME = "bella"
MAINTENANCE_DATABASE_NAME = "postgres"


def require_maintenance_database(admin_url: str) -> None:
    database_name = conninfo_to_dict(admin_url).get("dbname")
    if database_name != MAINTENANCE_DATABASE_NAME:
        raise ValueError(
            "POSTGRES_ADMIN_URL must point to the 'postgres' maintenance database; "
            f"got {database_name!r}"
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
