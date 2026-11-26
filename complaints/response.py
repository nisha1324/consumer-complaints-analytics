"""Part 3: how companies respond.

Every table comes from a file in sql/. The working choices are set once here:

* outcomes are read on final responses only ("In progress" has no outcome yet); an
  "Untimely response" is final and counts as no relief;
* "late" counts both forms of not timely (see sql/responses.sql);
* a company is compared with its peers on relief after allowing for its product x issue
  mix (sql/company_expected.sql), and only companies with MIN_RESPONSES or more final
  responses are compared;
* chance limits are the usual funnel-plot ones: the company is outside them when its
  observed count is more than Z95 / Z998 standard deviations from the expected count
  under the binomial spread chance alone would give;
* a change in practice during the year is a company with HALF_MIN or more final responses
  in each half whose relief rate moved by SHIFT_MIN or more (and beyond Z998).
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from complaints import load, mix

MIN_RESPONSES = 100
MIN_PEER = 30
Z95, Z998 = 1.959964, 3.090232
HALF_MIN = 250
SHIFT_MIN = 0.20
LOW, HIGH = 0.02, 0.90       # "almost never" / "almost always" relief, for the spread by product


def _df(con: duckdb.DuckDBPyConnection, query: str) -> pd.DataFrame:
    return con.execute(query).df()


def prepare(con: duckdb.DuckDBPyConnection) -> None:
    mix.prepare(con)
    con.execute(load.sql("responses"))


def connect() -> duckdb.DuckDBPyConnection:
    con = load.connect()
    prepare(con)
    return con


# ---------------------------------------------------------------- 1. outcomes by product

def by_product(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    d = _df(con, load.sql("response_by_product"))
    f = d["final_responses"]
    d["late"] = d["untimely_response"] + d["closed_late"]
    d["monetary_rate"] = d["monetary_relief"] / f
    d["non_monetary_rate"] = d["non_monetary_relief"] / f
    d["relief_rate"] = (d["monetary_relief"] + d["non_monetary_relief"]) / f
    d["explanation_rate"] = d["explanation"] / f
    d["late_rate"] = d["late"] / f
    return d


def totals(con: duckdb.DuckDBPyConnection) -> dict:
    r = con.execute("""
        SELECT count(*), sum(relief), sum(monetary), sum(late),
               count(*) FILTER (WHERE company_response = 'Untimely response'),
               count(DISTINCT company_merged)
        FROM responses""").fetchone()
    n, rel, mon, late, untimely, cos = (int(x) for x in r)
    return {"final_responses": n, "relief": rel, "monetary": mon, "late": late, "untimely_response": untimely,
            "closed_late": late - untimely, "companies": cos,
            "relief_rate": rel / n, "monetary_rate": mon / n, "late_rate": late / n}


# ---------------------------------------------------------------- 2. companies against peers

def company_expected(con: duckdb.DuckDBPyConnection, metric: str = "relief", where: str = "TRUE",
                     min_responses: int = MIN_RESPONSES) -> pd.DataFrame:
    """Observed against expected for each company with min_responses or more final responses.

    rate / expected_rate / difference are per final response; z is (observed - expected) / sd
    under chance alone; raw_difference compares with the all-company rate, ignoring mix."""
    if metric not in ("relief", "monetary"):
        raise ValueError(metric)
    q = load.sql("company_expected").replace("{metric}", metric).replace("{where}", where) \
        .replace("{min_peer}", str(MIN_PEER))
    d = _df(con, q)
    overall = d["observed"].sum() / d["final_responses"].sum()
    d = d[d["final_responses"] >= min_responses].copy()
    n = d["final_responses"]
    d["rate"] = d["observed"] / n
    d["expected_rate"] = d["expected"] / n
    d["difference"] = d["rate"] - d["expected_rate"]
    d["raw_difference"] = d["rate"] - overall
    d["z"] = (d["observed"] - d["expected"]) / np.sqrt(d["variance"])
    d["verdict"] = np.select([d["z"] > Z998, d["z"] < -Z998], ["above", "below"], "within")
    d["outside_95"] = d["z"].abs() > Z95
    d["overall_rate"] = overall
    return d.sort_values(["final_responses", "company"], ascending=[False, True], kind="stable").reset_index(drop=True)


def chance_summary(ce: pd.DataFrame) -> dict:
    k = len(ce)
    out998 = int((ce["verdict"] != "within").sum())
    return {"companies": k, "responses": int(ce["final_responses"].sum()),
            "outside_998": out998, "above": int((ce["verdict"] == "above").sum()),
            "below": int((ce["verdict"] == "below").sum()),
            "outside_95": int(ce["outside_95"].sum()),
            "chance_998": k * 0.002, "chance_95": k * 0.05}


def mix_effect(ce: pd.DataFrame, threshold: float = 0.05) -> dict:
    """How much allowing for mix changes the picture: companies that look 5+ points above (or below)
    the all-company rate on raw figures but are on the other side once mix is allowed for."""
    flips = ce[(np.sign(ce["raw_difference"]) != np.sign(ce["difference"]))
               & (ce["raw_difference"].abs() >= threshold)]
    return {"flips": flips.sort_values("final_responses", ascending=False, kind="stable"),
            "mean_abs_raw": float(ce["raw_difference"].abs().mean()),
            "mean_abs_adjusted": float(ce["difference"].abs().mean()),
            "threshold": threshold}


def spread_by_product(con: duckdb.DuckDBPyConnection, min_responses: int = MIN_RESPONSES) -> pd.DataFrame:
    """Relief rate of each company within one product: how many almost never / almost always give relief."""
    d = _df(con, f"""
        SELECT product, company_merged AS company, count(*) AS n, avg(relief) AS rate
        FROM responses GROUP BY ALL HAVING count(*) >= {int(min_responses)}""")
    rows = []
    for prod, g in d.groupby("product"):
        rows.append({"product": prod, "companies": len(g), "responses": int(g["n"].sum()),
                     "almost_never": int((g["rate"] < LOW).sum()), "almost_always": int((g["rate"] > HIGH).sum()),
                     "median_company": float(g["rate"].median()),
                     "p25": float(g["rate"].quantile(0.25)), "p75": float(g["rate"].quantile(0.75)),
                     "pooled": float(np.average(g["rate"], weights=g["n"]))})
    return pd.DataFrame(rows).sort_values(["responses", "product"], ascending=[False, True], kind="stable") \
        .reset_index(drop=True)


def issue_spread(con: duckdb.DuckDBPyConnection, product: str, issue: str,
                 min_responses: int = MIN_RESPONSES) -> pd.DataFrame:
    """Relief rate by company for one product and issue (to show the spread on a like-for-like cell)."""
    p, i = product.replace("'", "''"), issue.replace("'", "''")
    return _df(con, f"""
        SELECT company_merged AS company, count(*) AS n, sum(relief) AS relief, avg(relief) AS rate
        FROM responses WHERE product = '{p}' AND issue = '{i}'
        GROUP BY ALL HAVING count(*) >= {int(min_responses)}
        ORDER BY n DESC, company""")


# ---------------------------------------------------------------- 3. changes during the year

def halves(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    d = _df(con, load.sql("relief_halves")).fillna({"n1": 0, "n2": 0, "relief1": 0, "relief2": 0})
    N1, N2 = d["n1"].sum(), d["n2"].sum()
    d["rate1"] = d["relief1"] / d["n1"].where(d["n1"] > 0)
    d["rate2"] = d["relief2"] / d["n2"].where(d["n2"] > 0)
    d["shift"] = d["rate2"] - d["rate1"]
    pooled = (d["relief1"] + d["relief2"]) / (d["n1"] + d["n2"])
    se = np.sqrt(pooled * (1 - pooled) * (1 / d["n1"].where(d["n1"] > 0) + 1 / d["n2"].where(d["n2"] > 0)))
    d["z"] = d["shift"] / se.where(se > 0)
    # contribution of each company to the change in the all-company relief rate (sums to that change)
    d["contribution"] = d["relief2"] / N2 - d["relief1"] / N1
    return d.sort_values(["contribution", "company"], ascending=[False, True], kind="stable").reset_index(drop=True)


def shifts(h: pd.DataFrame) -> pd.DataFrame:
    big = h[(h["n1"] >= HALF_MIN) & (h["n2"] >= HALF_MIN) & (h["shift"].abs() >= SHIFT_MIN) & (h["z"].abs() > Z998)]
    return big.sort_values(["shift", "company"], ascending=[False, True], kind="stable").reset_index(drop=True)


def half_rates(h: pd.DataFrame) -> tuple[float, float]:
    return float(h["relief1"].sum() / h["n1"].sum()), float(h["relief2"].sum() / h["n2"].sum())


def by_month(con: duckdb.DuckDBPyConnection, exclude: tuple[str, ...] = ()) -> pd.DataFrame:
    where = "TRUE" if not exclude else "company_merged NOT IN (" + ", ".join(
        "'" + c.replace("'", "''") + "'" for c in exclude) + ")"
    return _df(con, load.sql("relief_by_month").replace("{where}", where))


def company_months(con: duckdb.DuckDBPyConnection, company: str) -> pd.DataFrame:
    c = company.replace("'", "''")
    return _df(con, f"""
        SELECT strftime(date_received, '%Y-%m') AS month, count(*) AS final_responses, sum(relief) AS relief,
               avg(relief) AS relief_rate
        FROM responses WHERE company_merged = '{c}' GROUP BY 1 ORDER BY 1""")


# ---------------------------------------------------------------- 4. timeliness

def late_by_company(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    d = _df(con, load.sql("late_by_company"))
    d["late_rate"] = d["late"] / d["final_responses"]
    d["cumulative_share"] = d["late"].cumsum() / d["late"].sum()
    d["rank"] = np.arange(1, len(d) + 1)
    return d


def late_summary(lt: pd.DataFrame) -> dict:
    late = lt[lt["late"] > 0]
    return {"late": int(lt["late"].sum()), "companies": len(lt), "companies_with_late": len(late),
            "companies_for_half": int((lt["cumulative_share"] < 0.5).sum() + 1),
            "companies_for_80": int((lt["cumulative_share"] < 0.8).sum() + 1),
            "top2_share": float(lt["late"].head(2).sum() / lt["late"].sum()),
            "large": int((lt["final_responses"] >= MIN_RESPONSES).sum()),
            "large_10pct": int(((lt["final_responses"] >= MIN_RESPONSES) & (lt["late_rate"] >= 0.10)).sum()),
            "large_zero": int(((lt["final_responses"] >= MIN_RESPONSES) & (lt["late"] == 0)).sum())}


# ---------------------------------------------------------------- 5. the repeats

def repeats_check(con: duckdb.DuckDBPyConnection, metric: str = "relief") -> dict:
    a = company_expected(con, metric)
    b = company_expected(con, metric, where="NOT is_repeat")
    m = a.merge(b, on="company", suffixes=("", "_nr"))
    changed = m[m["verdict"] != m["verdict_nr"]]
    return {"companies": len(a), "companies_nr": len(b), "both": len(m),
            "same_verdict": int((m["verdict"] == m["verdict_nr"]).sum()),
            "changed": changed[["company", "final_responses", "verdict", "verdict_nr", "difference", "difference_nr"]],
            "correlation": float(np.corrcoef(m["difference"], m["difference_nr"])[0, 1]),
            "max_shift": float((m["difference"] - m["difference_nr"]).abs().max())}
