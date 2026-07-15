"""Safety checks for Bella's database connection targets."""

from psycopg.conninfo import conninfo_to_dict


def require_database_name(
    database_url: str,
    expected_name: str,
    *,
    setting_name: str,
) -> None:
    database_name = conninfo_to_dict(database_url).get("dbname")
    if database_name != expected_name:
        raise ValueError(
            f"{setting_name} must point to the {expected_name!r} database; "
            f"got {database_name!r}"
        )
