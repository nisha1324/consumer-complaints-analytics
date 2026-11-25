"""Build the committed snapshot files from the CFPB bulk CSV.

Two outputs, both written in a fixed row order so a rebuild from the same
bulk file gives the same bytes:

* the row-level snapshot (Parquet, zstd): every complaint received in the
  window about a product other than credit reporting, with typed columns
  and snake_case names;
* the monthly history (CSV): complaints per month and product, as the
  product was named when the complaint was filed, for the whole database;
* the company history (Parquet, zstd, optional): complaints per month,
  product, sub-product and company, as filed, for the whole database. Part 2
  needs the sub-product to map old product names onto current ones, and the
  company to see who is behind a surge.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from complaints import source

# Bulk-file column -> snapshot column. Order here is the snapshot's order.
RENAME = {
    "Complaint ID": "complaint_id",
    "Date received": "date_received",
    "Date sent to company": "date_sent_to_company",
    "Product": "product",
    "Sub-product": "sub_product",
    "Issue": "issue",
    "Sub-issue": "sub_issue",
    "Company": "company",
    "State": "state",
    "ZIP code": "zip_code",
    "Tags": "tags",
    "Submitted via": "submitted_via",
    "Company response to consumer": "company_response",
    "Company public response": "company_public_response",
    "Timely response?": "timely_response",
}

_TYPED = {
    "complaint_id": 'CAST("Complaint ID" AS BIGINT)',
    "date_received": 'CAST("Date received" AS DATE)',
    "date_sent_to_company": 'CAST("Date sent to company" AS DATE)',
    # "Yes" / "No" in the source; anything else becomes NULL and is counted by the profile.
    "timely_response": """CASE "Timely response?" WHEN 'Yes' THEN TRUE WHEN 'No' THEN FALSE END""",
}


def connect(threads: int = 1) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    # One thread keeps the Parquet row groups, and so the file's bytes, stable.
    con.execute(f"SET threads = {int(threads)}")
    con.execute("SET preserve_insertion_order = true")
    con.execute("SET enable_progress_bar = false")
    return con


def _read_csv(csv_path: Path) -> str:
    # Every column as text: types are set explicitly below, so a malformed
    # value fails loudly instead of being guessed.
    return (
        f"read_csv('{Path(csv_path).as_posix()}', header = true, all_varchar = true, "
        "quote = '\"', escape = '\"', strict_mode = true)"
    )


def check_columns(con: duckdb.DuckDBPyConnection, csv_path: Path) -> list[str]:
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {_read_csv(csv_path)}").fetchall()]
    if tuple(cols) != source.BULK_COLUMNS:
        raise ValueError(f"unexpected bulk-file columns: {cols}")
    return cols


def snapshot_select(csv_path: Path, start: str = source.WINDOW_START, end: str = source.WINDOW_END) -> str:
    cols = ",\n  ".join(_TYPED.get(new, '"' + old + '"') + " AS " + new for old, new in RENAME.items())
    excluded = ", ".join("'" + p.replace("'", "''") + "'" for p in source.CREDIT_REPORTING_PRODUCTS)
    return f"""
SELECT
  {cols}
FROM {_read_csv(csv_path)}
WHERE CAST("Date received" AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
  AND "Product" NOT IN ({excluded})
ORDER BY complaint_id
"""


def monthly_select(csv_path: Path) -> str:
    return f"""
SELECT
  strftime(date_trunc('month', CAST("Date received" AS DATE)), '%Y-%m') AS month,
  "Product" AS product,
  count(*) AS complaints
FROM {_read_csv(csv_path)}
GROUP BY ALL
ORDER BY month, product
"""


def company_monthly_select(csv_path: Path) -> str:
    return f"""
SELECT
  strftime(date_trunc('month', CAST("Date received" AS DATE)), '%Y-%m') AS month,
  "Product" AS product,
  "Sub-product" AS sub_product,
  "Company" AS company,
  count(*) AS complaints
FROM {_read_csv(csv_path)}
GROUP BY ALL
ORDER BY month, product, sub_product NULLS FIRST, company
"""


def build(csv_path: Path, snapshot_path: Path = source.SNAPSHOT_PATH,
          monthly_path: Path = source.MONTHLY_PATH, company_path: Path | None = None,
          threads: int = 1) -> dict:
    """Write the outputs and return row counts for the manifest.

    The company history is written only when company_path is given, so the
    small hand-made tests can build the snapshot on its own.
    """
    con = connect(threads)
    check_columns(con, csv_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY ({snapshot_select(csv_path)}) TO '{snapshot_path.as_posix()}' "
        "(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 131072)"
    )
    monthly = con.execute(monthly_select(csv_path)).df()
    monthly.to_csv(monthly_path, index=False, lineterminator="\n")
    total = int(con.execute(f"SELECT count(*) FROM {_read_csv(csv_path)}").fetchone()[0])
    snap_rows = int(con.execute(f"SELECT count(*) FROM read_parquet('{snapshot_path.as_posix()}')").fetchone()[0])
    counts = {
        "bulk_rows": total,
        "snapshot_rows": snap_rows,
        "monthly_rows": int(len(monthly)),
        "monthly_total": int(monthly["complaints"].sum()),
    }
    if company_path is not None:
        con.execute(
            f"COPY ({company_monthly_select(csv_path)}) TO '{Path(company_path).as_posix()}' "
            "(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 131072)"
        )
        rows, tot = con.execute(
            f"SELECT count(*), sum(complaints) FROM read_parquet('{Path(company_path).as_posix()}')").fetchone()
        counts["company_monthly_rows"], counts["company_monthly_total"] = int(rows), int(tot)
    return counts
