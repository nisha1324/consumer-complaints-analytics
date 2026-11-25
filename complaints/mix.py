"""Part 2: where complaints come from.

Every table comes from a file in sql/. The working choices are set once here:

* the history ends with October 2026 (the bulk file stops on 23 November);
* a spike month is at least SPIKE_RATIO times the larger of two baselines
  (the median of the 12 months before and of the 6 months after) and at
  least MIN_EXCESS complaints above it: far above what came before *and*
  what came after, so a one-off, not a new level;
* weeks inside the FY2026 snapshot use the same ratio against the 8 weeks
  before and after, with WEEK_MIN_EXCESS.
"""
from __future__ import annotations

import duckdb
import pandas as pd

from complaints import load, taxonomy

LAST_MONTH = "2026-10"
SPIKE_RATIO = 1.5
MIN_EXCESS = 250
WEEK_MIN_EXCESS = 100
FIRST_WEEK, LAST_WEEK = "2025-10-06", "2026-09-21"   # the full Monday-to-Sunday weeks in FY2026
TREND_FROM = 2018   # first full fiscal year under the April 2017 product list


def _df(con: duckdb.DuckDBPyConnection, query: str) -> pd.DataFrame:
    return con.execute(query).df()


def prepare(con: duckdb.DuckDBPyConnection, ratio: float = SPIKE_RATIO, min_excess: int = MIN_EXCESS) -> None:
    """Register the product map and build the Part 2 views and tables on a load.connect() connection."""
    pairs = con.execute("SELECT DISTINCT product, sub_product FROM company_monthly").df()
    pm = taxonomy.map_table(pairs)
    con.register("product_map_df", pm)
    con.execute("CREATE OR REPLACE TABLE product_map AS SELECT * FROM product_map_df")
    con.unregister("product_map_df")
    con.execute(load.sql("company_names"))
    con.execute(load.sql("history"))
    con.execute(load.sql("product_months").replace("{last_month}", LAST_MONTH)
                .replace("{ratio}", repr(float(ratio))).replace("{min_excess}", str(int(min_excess))))
    con.execute(load.sql("flagged"))


def connect() -> duckdb.DuckDBPyConnection:
    con = load.connect()
    prepare(con)
    return con


# ---------------------------------------------------------------- 1. old names -> current products

def product_map(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Every (product, sub-product) pair as filed, its current product and complaints."""
    return _df(con, """
        SELECT m.product, m.sub_product, m.current_product, m.rule,
               min(h.month) AS first_month, max(h.month) AS last_month, sum(h.complaints) AS complaints
        FROM product_map m
        JOIN company_monthly h ON h.product = m.product AND h.sub_product IS NOT DISTINCT FROM m.sub_product
        GROUP BY ALL
        ORDER BY m.current_product, m.product, m.sub_product NULLS FIRST
    """)


def map_summary(pm: pd.DataFrame) -> pd.DataFrame:
    """Old names (anything not filed under a current name) by current product."""
    old = pm[pm["rule"] != "same name"]
    return (old.groupby(["current_product", "product"], as_index=False)
            .agg(sub_products=("sub_product", "size"), complaints=("complaints", "sum"),
                 first_month=("first_month", "min"), last_month=("last_month", "max"))
            .sort_values(["current_product", "complaints"], ascending=[True, False], kind="stable")
            .reset_index(drop=True))


# ---------------------------------------------------------------- 2. spikes and trends

def product_months(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _df(con, "SELECT * FROM product_months ORDER BY current_product, month")


def spikes(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Spike months with the company split of the excess over the product's 12-month average."""
    pmo = product_months(con)
    sp = pmo[pmo["status"] == "spike"].copy()
    comp = spike_companies(con)
    rows = []
    for r in sp.itertuples(index=False):
        c = comp[(comp["current_product"] == r.current_product) & (comp["month"] == r.month)]
        excess = c["excess"].sum()                       # = complaints - the product's 12-month average
        top = c.sort_values(["excess", "company"], ascending=[False, True], kind="stable").head(2)
        rows.append({
            "current_product": r.current_product, "month": r.month, "complaints": int(r.complaints),
            "baseline": float(r.baseline), "ratio": r.complaints / r.baseline,
            "excess_over_baseline": float(r.complaints - r.baseline),
            "prior_average": float(c["prior_average"].sum()), "excess_over_average": float(excess),
            "top_company": top["company"].iloc[0], "top_company_excess": float(top["excess"].iloc[0]),
            "top_company_share": float(top["excess"].iloc[0] / excess),
            "second_company": top["company"].iloc[1] if len(top) > 1 else None,
            "second_company_share": float(top["excess"].iloc[1] / excess) if len(top) > 1 else float("nan"),
        })
    return pd.DataFrame(rows).sort_values(["month", "current_product"], kind="stable").reset_index(drop=True)


def spike_companies(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _df(con, load.sql("spike_companies"))


def recent_flags(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    pmo = product_months(con)
    return pmo[pmo["status"] == "recent"].reset_index(drop=True)


def fiscal_years(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Complaints per fiscal year and current product, as counted and with spike months at their baseline."""
    pmo = product_months(con)
    pmo = pmo[pmo["fiscal_year"] <= 2026]
    out = (pmo.assign(adjusted=pmo["complaints"].where(pmo["status"] != "spike", pmo["baseline"]),
                      spike_months=(pmo["status"] == "spike").astype(int))
           .groupby(["current_product", "fiscal_year"], as_index=False)
           .agg(complaints=("complaints", "sum"), adjusted=("adjusted", "sum"),
                spike_months=("spike_months", "sum"), months=("month", "size")))
    out["complaints"] = out["complaints"].astype("int64")
    return out


def growth(fy: pd.DataFrame) -> pd.DataFrame:
    """FY2025 -> FY2026 and FY2019 -> FY2026 change per current product, as counted and without spikes."""
    p = fy.pivot(index="current_product", columns="fiscal_year")
    out = pd.DataFrame({
        "fy2019": p[("complaints", 2019)], "fy2025": p[("complaints", 2025)], "fy2026": p[("complaints", 2026)],
        "fy2025_adjusted": p[("adjusted", 2025)], "fy2026_adjusted": p[("adjusted", 2026)],
        "fy2019_adjusted": p[("adjusted", 2019)],
        "spike_months_2025": p[("spike_months", 2025)], "spike_months_2026": p[("spike_months", 2026)],
    })
    out["change_1y"] = out["fy2026"] / out["fy2025"] - 1
    out["change_1y_adjusted"] = out["fy2026_adjusted"] / out["fy2025_adjusted"] - 1
    out["change_7y"] = out["fy2026"] / out["fy2019"] - 1
    out["change_7y_adjusted"] = out["fy2026_adjusted"] / out["fy2019_adjusted"] - 1
    order = {p: i for i, p in enumerate(taxonomy.CURRENT_PRODUCTS)}
    return out.reset_index().sort_values("current_product", key=lambda s: s.map(order)).reset_index(drop=True)


def change_by_company(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _df(con, load.sql("fy_change_by_company"))


def change_drivers(chg: pd.DataFrame, top: int = 3) -> pd.DataFrame:
    """Per product: the change in complaints per month (spike months left out), the companies that
    added most, and how much of the change the largest one makes up."""
    rows = []
    for prod, g in chg.groupby("current_product", sort=False):
        total = g["change_per_month"].sum()
        up = g.sort_values(["change_per_month", "company"], ascending=[False, True], kind="stable")
        down = g.sort_values(["change_per_month", "company"], ascending=[True, True], kind="stable")
        lead = up if total >= 0 else down
        rows.append({
            "current_product": prod,
            "per_month_2025": g["per_month_2025"].sum(), "per_month_2026": g["per_month_2026"].sum(),
            "change_per_month": total,
            "months_2025": int(g["months_2025"].iloc[0]), "months_2026": int(g["months_2026"].iloc[0]),
            "lead_company": lead["company"].iloc[0], "lead_change": lead["change_per_month"].iloc[0],
            "lead_share": lead["change_per_month"].iloc[0] / total if total else float("nan"),
            "top_companies": "; ".join(f"{c} ({v:+,.0f})" for c, v in
                                       zip(lead["company"].head(top), lead["change_per_month"].head(top))),
            "companies_up": int((g["change_per_month"] > 0).sum()),
            "companies_down": int((g["change_per_month"] < 0).sum()),
        })
    out = pd.DataFrame(rows)
    order = {p: i for i, p in enumerate(taxonomy.CURRENT_PRODUCTS)}
    return out.sort_values("current_product", key=lambda s: s.map(order)).reset_index(drop=True)


def weekly(con: duckdb.DuckDBPyConnection, ratio: float = SPIKE_RATIO, min_excess: int = WEEK_MIN_EXCESS) -> pd.DataFrame:
    q = (load.sql("weekly_spikes").replace("{first_week}", FIRST_WEEK).replace("{last_week}", LAST_WEEK)
         .replace("{ratio}", repr(float(ratio))).replace("{min_excess}", str(int(min_excess))))
    return _df(con, q)


def sensitivity(con: duckdb.DuckDBPyConnection, settings=((1.3, 250), (1.5, 100), (1.5, 250), (2.0, 250))) -> pd.DataFrame:
    """How many spike months, and how many inside FY2026, under other thresholds."""
    rows = []
    for ratio, min_excess in settings:
        c = load.connect()
        prepare(c, ratio, min_excess)
        pmo = product_months(c)
        sp = pmo[pmo["status"] == "spike"]
        rows.append({"ratio": ratio, "min_excess": min_excess, "spike_months": len(sp),
                     "products": sp["current_product"].nunique(),
                     "in_fy2026": int((sp["fiscal_year"] == 2026).sum()),
                     "in_fy2025": int((sp["fiscal_year"] == 2025).sum())})
        c.close()
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 3. FY2026 issues, and the repeats

def issue_mix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _df(con, load.sql("issue_mix"))


def top_issues(mix: pd.DataFrame, k: int = 3) -> pd.DataFrame:
    out = mix.sort_values(["product", "complaints", "issue"], ascending=[True, False, True], kind="stable")
    out = out.groupby("product", sort=False).head(k).copy()
    out["rank"] = out.groupby("product").cumcount() + 1
    return out.reset_index(drop=True)


def robustness(con: duckdb.DuckDBPyConnection) -> dict:
    """Key Part 1/2 figures with and without the repeats (company names merged in both)."""
    prod = _df(con, """
        SELECT product, count(*) AS complaints, count(*) FILTER (WHERE NOT is_repeat) AS complaints_no_repeats
        FROM complaints_flagged GROUP BY ALL ORDER BY complaints DESC, product
    """)
    prod["share"] = prod["complaints"] / prod["complaints"].sum()
    prod["share_no_repeats"] = prod["complaints_no_repeats"] / prod["complaints_no_repeats"].sum()
    prod["rank"] = prod["complaints"].rank(ascending=False, method="first").astype(int)
    prod["rank_no_repeats"] = prod["complaints_no_repeats"].rank(ascending=False, method="first").astype(int)

    comp = _df(con, """
        SELECT company_merged AS company, count(*) AS complaints,
               count(*) FILTER (WHERE NOT is_repeat) AS complaints_no_repeats
        FROM complaints_flagged GROUP BY ALL
    """)

    def ranking(col: str) -> pd.DataFrame:
        d = comp[comp[col] > 0].sort_values([col, "company"], ascending=[False, True], kind="stable").reset_index(drop=True)
        d["rank"] = d.index + 1
        d["cumulative_share"] = d[col].cumsum() / d[col].sum()
        return d

    with_r, without_r = ranking("complaints"), ranking("complaints_no_repeats")

    def summary(d: pd.DataFrame, col: str) -> dict:
        return {"companies": int(len(d)), "top10_share": float(d[col].head(10).sum() / d[col].sum()),
                "companies_for_half": int((d["cumulative_share"] < 0.5).sum() + 1),
                "single_complaint_companies": int((d[col] == 1).sum())}

    top10 = with_r.head(10)[["company", "rank"]].merge(
        without_r[["company", "rank"]], on="company", how="left", suffixes=("", "_no_repeats"))
    mix = issue_mix(con)
    tops = top_issues(mix, 1).set_index("product")
    tops_nr = (mix.sort_values(["product", "complaints_no_repeats", "issue"], ascending=[True, False, True],
                               kind="stable").groupby("product").head(1).set_index("product"))
    return {
        "products": prod,
        "with": summary(with_r, "complaints"), "without": summary(without_r, "complaints_no_repeats"),
        "top10": top10,
        "top10_same_set": set(with_r.head(10)["company"]) == set(without_r.head(10)["company"]),
        "top_issue_same": bool((tops["issue"] == tops_nr.loc[tops.index, "issue"]).all()),
        "max_issue_share_shift": float((mix["share"] - mix["share_no_repeats"]).abs().max()),
        "max_product_share_shift": float((prod["share"] - prod["share_no_repeats"]).abs().max()),
        "merged_companies": int(con.execute(
            "SELECT count(DISTINCT company) - count(DISTINCT company_merged) FROM complaints_flagged").fetchone()[0]),
        "merged_complaints": int(con.execute("""
            SELECT count(*) FROM complaints_flagged
            WHERE company_merged IN (SELECT company_merged FROM complaints_flagged
                                     GROUP BY 1 HAVING count(DISTINCT company) > 1)""").fetchone()[0]),
    }
