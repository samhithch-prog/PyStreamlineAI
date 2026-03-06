import argparse
import os
from collections import deque

try:
    import psycopg
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"psycopg is required for migration: {exc}")


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def fq_table(schema: str, table: str) -> str:
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def get_tables(conn: psycopg.Connection, schema: str) -> list[str]:
    with conn.cursor() as cur:
        rows = cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (schema,),
        ).fetchall()
    return [str(r[0]) for r in rows]


def get_foreign_key_edges(conn: psycopg.Connection, schema: str) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        rows = cur.execute(
            """
            SELECT
                ccu.table_name AS parent_table,
                tc.table_name AS child_table
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s
            """,
            (schema,),
        ).fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def order_tables_for_insert(tables: list[str], fk_edges: list[tuple[str, str]]) -> list[str]:
    table_set = set(tables)
    children_by_parent = {table: set() for table in tables}
    in_degree = {table: 0 for table in tables}

    for parent, child in fk_edges:
        if parent == child:
            continue
        if parent not in table_set or child not in table_set:
            continue
        if child in children_by_parent[parent]:
            continue
        children_by_parent[parent].add(child)
        in_degree[child] += 1

    queue = deque(sorted(table for table, degree in in_degree.items() if degree == 0))
    ordered: list[str] = []

    while queue:
        table = queue.popleft()
        ordered.append(table)
        for child in sorted(children_by_parent[table]):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
                queue = deque(sorted(queue))

    if len(ordered) != len(tables):
        remaining = sorted(set(tables) - set(ordered))
        print(
            "warning: foreign-key cycle detected; appending unresolved tables in lexical order: "
            + ", ".join(remaining)
        )
        ordered.extend(remaining)

    return ordered


def get_columns(conn: psycopg.Connection, schema: str, table: str) -> list[str]:
    with conn.cursor() as cur:
        rows = cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table),
        ).fetchall()
    return [str(r[0]) for r in rows]


def truncate_tables(conn: psycopg.Connection, schema: str, tables: list[str]) -> None:
    if not tables:
        return
    table_sql = ", ".join(fq_table(schema, table) for table in reversed(tables))
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {table_sql} RESTART IDENTITY CASCADE")


def reset_id_sequence(conn: psycopg.Connection, schema: str, table: str) -> None:
    with conn.cursor() as cur:
        row = cur.execute(
            "SELECT pg_get_serial_sequence(%s, 'id')",
            (f"{schema}.{table}",),
        ).fetchone()
        if row is None or row[0] is None:
            return
        sequence_name = str(row[0])
        cur.execute(
            f"SELECT setval(%s::regclass, COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) "
            f"FROM {fq_table(schema, table)}",
            (sequence_name,),
        )


def migrate_table(
    source_conn: psycopg.Connection,
    target_conn: psycopg.Connection,
    schema: str,
    table: str,
    batch_size: int,
) -> int:
    source_columns = get_columns(source_conn, schema, table)
    target_columns = set(get_columns(target_conn, schema, table))
    columns = [column for column in source_columns if column in target_columns]
    if not columns:
        print(f"skip {table}: no shared columns between source and target")
        return 0

    column_sql = ", ".join(quote_ident(column) for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    select_sql = f"SELECT {column_sql} FROM {fq_table(schema, table)}"
    insert_sql = f"INSERT INTO {fq_table(schema, table)} ({column_sql}) VALUES ({placeholders})"

    total_rows = 0
    with source_conn.cursor() as source_cur, target_conn.cursor() as target_cur:
        source_cur.execute(select_sql)
        while True:
            rows = source_cur.fetchmany(batch_size)
            if not rows:
                break
            target_cur.executemany(insert_sql, rows)
            total_rows += len(rows)

    if "id" in columns:
        reset_id_sequence(target_conn, schema, table)

    return total_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate data from one PostgreSQL database to another.")
    parser.add_argument(
        "--source-url",
        default=os.getenv("SOURCE_DATABASE_URL", os.getenv("DATABASE_URL", "")),
        help="Source PostgreSQL URL. Defaults to SOURCE_DATABASE_URL, then DATABASE_URL.",
    )
    parser.add_argument(
        "--target-url",
        default=os.getenv("TARGET_DATABASE_URL", ""),
        help="Target PostgreSQL URL. Defaults to TARGET_DATABASE_URL.",
    )
    parser.add_argument(
        "--schema",
        default="public",
        help="Schema to migrate. Defaults to public.",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        default=[],
        help="Optional explicit table list. Defaults to all base tables in the schema.",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Optional table list to exclude.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Rows to copy per insert batch.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate target tables before import.",
    )
    args = parser.parse_args()

    source_url = str(args.source_url).strip()
    target_url = str(args.target_url).strip()

    if not source_url:
        raise SystemExit("Missing source PostgreSQL URL. Set --source-url or SOURCE_DATABASE_URL.")
    if not target_url:
        raise SystemExit("Missing target PostgreSQL URL. Set --target-url or TARGET_DATABASE_URL.")
    if "[YOUR-PASSWORD]" in source_url or "[YOUR-PASSWORD]" in target_url:
        raise SystemExit("Replace [YOUR-PASSWORD] placeholder with the real database password.")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be a positive integer.")

    source_conn = psycopg.connect(source_url)
    target_conn = psycopg.connect(target_url)

    try:
        source_tables = get_tables(source_conn, args.schema)
        if not source_tables:
            raise SystemExit(f"No source tables found in schema '{args.schema}'.")

        source_table_set = set(source_tables)
        requested_tables = args.tables if args.tables else source_tables
        missing_in_source = [table for table in requested_tables if table not in source_table_set]
        for table in missing_in_source:
            print(f"skip {table}: missing in source schema")

        excluded_set = set(args.exclude)
        selected_tables = [
            table for table in requested_tables if table in source_table_set and table not in excluded_set
        ]
        if not selected_tables:
            raise SystemExit("No tables selected for migration after filters.")

        fk_edges = get_foreign_key_edges(source_conn, args.schema)
        ordered_tables = order_tables_for_insert(selected_tables, fk_edges)

        target_tables = set(get_tables(target_conn, args.schema))
        migratable_tables = [table for table in ordered_tables if table in target_tables]
        skipped_missing_target = [table for table in ordered_tables if table not in target_tables]
        for table in skipped_missing_target:
            print(f"skip {table}: missing in target schema")

        if args.truncate:
            truncate_tables(target_conn, args.schema, migratable_tables)

        total = 0
        for table in migratable_tables:
            count = migrate_table(source_conn, target_conn, args.schema, table, args.batch_size)
            total += count
            print(f"migrated {table}: {count}")

        target_conn.commit()
        print(f"done. total rows migrated: {total}")
    except Exception:
        target_conn.rollback()
        raise
    finally:
        source_conn.close()
        target_conn.close()


if __name__ == "__main__":
    main()
