from __future__ import annotations

import argparse
from collections.abc import Iterable

from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infrastructure.db.session import create_engine_from_url


def _iter_rows(session: Session, table: Table, batch_size: int) -> Iterable[dict]:
    stmt = select(table)
    result = session.execute(stmt).mappings()
    while True:
        rows = result.fetchmany(batch_size)
        if not rows:
            return
        for row in rows:
            yield dict(row)


def import_sqlite_data(*, src_sqlite_path: str, dest_url: str, batch_size: int = 500) -> None:
    src_engine = create_engine(f"sqlite+pysqlite:///{src_sqlite_path}", future=True)
    dest_engine = create_engine_from_url(dest_url)

    src_md = MetaData()
    dest_md = MetaData()
    src_md.reflect(bind=src_engine)
    dest_md.reflect(bind=dest_engine)

    tables = [
        "runs",
        "drafts",
        "posts",
        "publish_attempts",
        "action_tokens",
        "auth_users",
        "auth_sessions",
        "audit_logs",
        "agent_logs",
        "app_config",
    ]

    with Session(src_engine) as src_sess, Session(dest_engine) as dest_sess:
        for name in tables:
            src_table = src_md.tables.get(name)
            dest_table = dest_md.tables.get(name)
            if src_table is None or dest_table is None:
                continue

            dest_cols = {c.name for c in dest_table.columns}
            src_cols = {c.name for c in src_table.columns}
            common_cols = sorted(dest_cols & src_cols)
            if not common_cols:
                continue

            inserted = 0
            for row in _iter_rows(src_sess, src_table, batch_size=batch_size):
                payload = {k: row.get(k) for k in common_cols}
                try:
                    dest_sess.execute(dest_table.insert().values(**payload))
                    inserted += 1
                except IntegrityError:
                    dest_sess.rollback()
                else:
                    if inserted % batch_size == 0:
                        dest_sess.commit()
            dest_sess.commit()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True, help="Path to legacy SQLite DB file")
    p.add_argument(
        "--dest-url",
        required=True,
        help="Destination SQLAlchemy URL (e.g. postgresql+psycopg://... or sqlite+pysqlite:///...)",
    )
    p.add_argument("--batch-size", type=int, default=500)
    args = p.parse_args()

    import_sqlite_data(
        src_sqlite_path=str(args.src), dest_url=str(args.dest_url), batch_size=int(args.batch_size)
    )


if __name__ == "__main__":
    main()
