import argparse
import os
import sqlite3
from typing import Iterable

try:
    import psycopg
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"psycopg is required for migration: {exc}")

TABLE_ORDER = [
    "users",
    "chat_sessions",
    "analysis_history",
    "auth_sessions",
    "user_login_events",
    "chat_history",
    "promo_codes",
    "promo_redemptions",
]


def sqlite_has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def get_sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def chunked(rows: list[tuple], size: int = 500) -> Iterable[list[tuple]]:
    for idx in range(0, len(rows), size):
        yield rows[idx : idx + size]


def migrate_table(sqlite_conn: sqlite3.Connection, pg_conn: psycopg.Connection, table: str) -> int:
    columns = get_sqlite_columns(sqlite_conn, table)
    if not columns:
        return 0

    rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return 0

    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    with pg_conn.cursor() as cur:
        for batch in chunked(rows):
            cur.executemany(insert_sql, batch)

        if "id" in columns:
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM {table}"
            )

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate local SQLite data to PostgreSQL.")
    parser.add_argument("--sqlite-path", default="users.db", help="Path to SQLite database")
    parser.add_argument(
        "--pg-url",
        default=os.getenv("DATABASE_URL", ""),
        help="PostgreSQL connection URL. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate target tables before import (recommended for first migration).",
    )
    args = parser.parse_args()

    if not args.pg_url:
        raise SystemExit("Missing PostgreSQL URL. Set --pg-url or DATABASE_URL.")

    sqlite_conn = sqlite3.connect(args.sqlite_path)
    pg_conn = psycopg.connect(args.pg_url)

    try:
        if args.truncate:
            with pg_conn.cursor() as cur:
                cur.execute(
                    "TRUNCATE TABLE promo_redemptions, promo_codes, chat_history, auth_sessions, "
                    "analysis_history, chat_sessions, users RESTART IDENTITY CASCADE"
                )

        total = 0
        for table in TABLE_ORDER:
            if not sqlite_has_table(sqlite_conn, table):
                print(f"skip {table}: not found in sqlite")
                continue
            count = migrate_table(sqlite_conn, pg_conn, table)
            total += count
            print(f"migrated {table}: {count}")

        pg_conn.commit()
        print(f"done. total rows migrated: {total}")
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
