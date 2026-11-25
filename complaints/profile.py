"""Part 1: profile the snapshot. Every table here comes from a file in sql/."""
from __future__ import annotations

import duckdb
import pandas as pd

from complaints import load

COLUMNS = (
    "complaint_id", "date_received", "date_sent_to_company", "product", "sub_product", "issue",
    "sub_issue", "company", "state", "zip_code", "tags", "submitted_via", "company_response",
    "company_public_response", "timely_response",
)


def _df(con: duckdb.DuckDBPyConnection, query: str) -> pd.DataFrame:
    return con.execute(query).df()


def column_profile(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    template = load.sql("column_profile")
    out = pd.concat([_df(con, template.replace("{col}", c)) for c in COLUMNS], ignore_index=True)
    out["filled_share"] = out["filled"] / out["complaints"]
    out["most_common_share"] = out["most_common_complaints"] / out["filled"]
    return out


def quality_checks(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    out = _df(con, load.sql("quality_checks"))
    total = con.execute("SELECT count(*) FROM complaints").fetchone()[0]
    out["share"] = out["complaints"] / total
    return out


def history(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    out = _df(con, load.sql("history_by_fiscal_year"))
    out["credit_reporting"] = out["credit_reporting"].fillna(0).astype("int64")
    out["complaints"] = out["complaints"].astype("int64")
    out["other_products"] = out["complaints"] - out["credit_reporting"]
    out["credit_reporting_share"] = out["credit_reporting"] / out["complaints"]
    return out


def monthly_split(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Complaints per month: credit reporting and all other products (for chart 01)."""
    return _df(con, """
        SELECT month,
               sum(complaints) FILTER (WHERE product ILIKE 'Credit reporting%') AS credit_reporting,
               sum(complaints) FILTER (WHERE NOT product ILIKE 'Credit reporting%') AS other_products
        FROM monthly GROUP BY month ORDER BY month
    """).fillna(0)


def product_mix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _df(con, load.sql("product_mix"))


def concentration(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _df(con, load.sql("company_concentration"))


def concentration_summary(conc: pd.DataFrame) -> dict:
    """Companies needed to reach a share of all complaints, and the long tail."""
    def companies_for(share: float) -> int:
        return int((conc["cumulative_share"] < share).sum() + 1)

    return {
        "companies": int(len(conc)),
        "top10_share": float(conc.loc[conc["rank"] <= 10, "complaints"].sum() / conc["complaints"].sum()),
        "companies_for_half": companies_for(0.5),
        "companies_for_80": companies_for(0.8),
        "single_complaint_companies": int((conc["complaints"] == 1).sum()),
    }


def response_by_month(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _df(con, load.sql("response_by_month"))


def repeats_by_product(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _df(con, load.sql("repeats_by_product"))


def name_collisions(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _df(con, load.sql("name_collisions"))


def sending_lag(con: duckdb.DuckDBPyConnection) -> dict:
    """Days from the CFPB receiving a complaint to sending it to the company."""
    row = con.execute("""
        SELECT quantile_disc(d, 0.5), quantile_disc(d, 0.9), quantile_disc(d, 0.99), max(d),
               avg(CASE WHEN d = 0 THEN 1.0 ELSE 0 END)
        FROM (SELECT date_sent_to_company - date_received AS d FROM complaints)
    """).fetchone()
    return {"median": int(row[0]), "p90": int(row[1]), "p99": int(row[2]), "max": int(row[3]),
            "same_day_share": float(row[4])}


def old_in_progress(con: duckdb.DuckDBPyConnection, before: str = "2026-08-01") -> pd.DataFrame:
    """Complaints still 'In progress' though received well before the snapshot, by company."""
    return _df(con, f"""
        SELECT company, count(*) AS complaints
        FROM complaints
        WHERE company_response = 'In progress' AND date_received < DATE '{before}'
        GROUP BY company ORDER BY complaints DESC, company
    """)


def surge_month(con: duckdb.DuckDBPyConnection) -> dict:
    """The month with the most complaints about products other than credit reporting, with its neighbours."""
    split = monthly_split(con).reset_index(drop=True)
    i = int(split["other_products"].idxmax())
    m = split.loc[i, "month"]
    prev_m = split.loc[i - 1, "month"]

    def count(month: str, like: str) -> int:
        return int(con.execute(
            "SELECT coalesce(sum(complaints), 0) FROM monthly WHERE month = ? AND product LIKE ?",
            [month, like]).fetchone()[0])

    out = {
        "month": m,
        "month_name": pd.Timestamp(m + "-01").strftime("%B %Y"),
        "complaints": int(split.loc[i, "other_products"]),
        "prev_complaints": int(split.loc[i - 1, "other_products"]),
        "next_complaints": int(split.loc[i + 1, "other_products"]),
        "mt": count(m, "Money transfer%"), "mt_prev": count(prev_m, "Money transfer%"),
        "bank": count(m, "Checking or savings%"), "bank_prev": count(prev_m, "Checking or savings%"),
    }
    out["jump_share"] = ((out["mt"] - out["mt_prev"]) + (out["bank"] - out["bank_prev"])) / (
        out["complaints"] - out["prev_complaints"])
    return out
