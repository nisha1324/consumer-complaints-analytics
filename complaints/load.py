"""Open the committed snapshot in DuckDB.

Three views:
* complaints:      the row-level FY2026 snapshot (one row per complaint)
* monthly:         complaints per month and product, full history
* company_monthly: complaints per month, product, sub-product and company, full history
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from complaints import source

SQL_DIR = source.ROOT / "sql"


def connect(snapshot: Path = source.SNAPSHOT_PATH, monthly: Path = source.MONTHLY_PATH,
            company_monthly: Path = source.COMPANY_MONTHLY_PATH) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET threads = 1")
    con.execute("SET enable_progress_bar = false")
    con.execute(f"CREATE VIEW complaints AS SELECT * FROM read_parquet('{Path(snapshot).as_posix()}')")
    con.execute(
        f"CREATE VIEW monthly AS SELECT month, product, CAST(complaints AS BIGINT) AS complaints "
        f"FROM read_csv('{Path(monthly).as_posix()}', header = true, "
        "columns = {'month': 'VARCHAR', 'product': 'VARCHAR', 'complaints': 'BIGINT'})"
    )
    con.execute(f"CREATE VIEW company_monthly AS SELECT * FROM read_parquet('{Path(company_monthly).as_posix()}')")
    return con


def sql(name: str) -> str:
    return (SQL_DIR / f"{name}.sql").read_text()
