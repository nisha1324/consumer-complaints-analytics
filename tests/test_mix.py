"""Part 2: the product map, the spike rule, the company splits and the repeats check.

First on a hand-made history where every expected value is worked out by hand, then on the
committed data.
"""
from __future__ import annotations

import re

import duckdb
import pandas as pd
import pytest

from complaints import build, load, mix as M, profile as P, source, taxonomy as T
from scripts import sources_report
from tests.conftest import write_bulk

RESULTS = source.ROOT / "results"


# ---------------------------------------------------------------- hand-made history

def _months(start: str, end: str) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end, freq="M")]


def _toy_history() -> pd.DataFrame:
    rows = []
    # Mortgage, ACME BANK: 100 a month 2020-01 .. 2021-06, then a new level of 400 a month to the end
    # of the history (a series that stopped would read as a spike against the zeros after it).
    for m in _months("2020-01", M.LAST_MONTH):
        n = 400 if m >= "2021-07" else 100
        n = {"2021-01": 300, "2021-03": 200}.get(m, n)
        rows.append((m, "Mortgage", "Conventional home mortgage", "ACME BANK", n))
    # 2021-01 also has 100 from a company with no complaints before: product 400 against a baseline of 100.
    rows.append(("2021-01", "Mortgage", "Conventional home mortgage", "Newcomer LLC", 100))
    # Old names that are split by sub-product, and a name spelled two ways.
    rows.append(("2018-05", "Credit card or prepaid card", "Gift card", "Acme Bank", 7))
    rows.append(("2018-05", "Credit card or prepaid card", "Store credit card", "ACME BANK,", 2))
    rows.append(("2016-02", "Consumer Loan", "Vehicle lease", "Acme Bank", 3))
    rows.append(("2016-04", "Consumer Loan", "Installment loan", "Acme Bank", 1))
    return pd.DataFrame(rows, columns=["month", "product", "sub_product", "company", "complaints"])


@pytest.fixture(scope="module")
def toy(tmp_path_factory):
    d = tmp_path_factory.mktemp("toy2")
    hist = _toy_history()
    comp = d / "company.parquet"
    duckdb.register("h", hist)
    duckdb.execute(f"COPY (SELECT month, product, sub_product, company, CAST(complaints AS BIGINT) AS complaints "
                   f"FROM h) TO '{comp}' (FORMAT parquet)")
    duckdb.unregister("h")
    from tests.conftest import bulk_row
    csv_path = write_bulk(d / "c.csv", [bulk_row(1), bulk_row(2), bulk_row(3, company="Acme Bank")])
    build.build(csv_path, d / "s.parquet", d / "m.csv")
    con = load.connect(d / "s.parquet", d / "m.csv", comp)
    M.prepare(con)
    return con


def test_current_product_rules():
    assert T.current_product("Credit card or prepaid card", "Gift card") == T.PREPAID
    assert T.current_product("Credit card or prepaid card", "Store credit card") == T.CREDIT_CARD
    assert T.current_product("Consumer Loan", "Vehicle lease") == T.VEHICLE
    assert T.current_product("Consumer Loan", "Pawn loan") == T.PAYDAY
    assert T.current_product("Credit reporting, credit repair services, or other personal consumer reports",
                             "Credit repair services") == T.DEBT_MGMT
    assert T.current_product("Credit reporting, credit repair services, or other personal consumer reports",
                             "Credit reporting") == T.CREDIT_REPORTING
    assert T.current_product(T.MONEY, "Debt settlement") == T.DEBT_MGMT
    assert T.current_product(T.MONEY, "Virtual currency") == T.MONEY
    assert T.current_product("Mortgage", "VA mortgage") == T.MORTGAGE
    assert T.current_product("Credit card", None) == T.CREDIT_CARD


def test_toy_map_and_merge(toy):
    pm = M.product_map(toy).set_index(["product", "sub_product"])
    assert pm.loc[("Credit card or prepaid card", "Gift card"), "current_product"] == T.PREPAID
    assert pm.loc[("Credit card or prepaid card", "Gift card"), "rule"] == "sub-product"
    assert pm.loc[("Consumer Loan", "Installment loan"), "rule"] == "renamed"
    assert pm.loc[("Mortgage", "Conventional home mortgage"), "rule"] == "same name"
    names = toy.execute("SELECT company, company_merged FROM company_names ORDER BY company").df()
    # "ACME BANK" has the most complaints in the history, so the other two spellings merge into it
    assert names.set_index("company")["company_merged"].to_dict() == {
        "ACME BANK": "ACME BANK", "ACME BANK,": "ACME BANK", "Acme Bank": "ACME BANK",
        "Newcomer LLC": "Newcomer LLC"}
    assert set(toy.execute("SELECT DISTINCT company FROM history").df()["company"]) == {"ACME BANK", "Newcomer LLC"}
    may18 = toy.execute("SELECT current_product, company, complaints FROM history WHERE month = '2018-05' "
                        "ORDER BY current_product").fetchall()
    assert may18 == [(T.CREDIT_CARD, "ACME BANK", 2), (T.PREPAID, "ACME BANK", 7)]
    total = toy.execute("SELECT sum(complaints) FROM history").fetchone()[0]
    assert total == _toy_history()["complaints"].sum()


def test_toy_spike_rule(toy):
    pmo = M.product_months(toy)
    mort = pmo[pmo["current_product"] == T.MORTGAGE].set_index("month")
    assert mort.index[0] == "2020-01" and mort.index[-1] == M.LAST_MONTH
    jan = mort.loc["2021-01"]
    assert (jan["complaints"], jan["prior_median"], jan["next_median"]) == (400, 100, 100)
    assert jan["status"] == "spike" and jan["baseline"] == 100
    # twice the baseline but only 100 above it: not a spike
    assert pd.isna(mort.loc["2021-03", "status"])
    # a new level is not a spike: 2021-07 is 4x the months before, but no higher than the months after
    assert mort.loc["2021-07", "prior_median"] == 100 and mort.loc["2021-07", "next_median"] == 400
    assert pd.isna(mort.loc["2021-07", "status"])
    assert (mort["status"] == "spike").sum() == 1
    # months with fewer than 12 before have no baseline
    assert mort.loc[:"2020-12", "prior_median"].isna().all()
    # prepaid: one month of data, so later months are zero-filled
    pre = pmo[pmo["current_product"] == T.PREPAID]
    assert pre["month"].iloc[0] == "2018-05" and pre["complaints"].iloc[0] == 7 and pre["complaints"].iloc[1:].eq(0).all()


def test_toy_spike_companies_add_up(toy):
    sp = M.spikes(toy)
    assert len(sp) == 1
    r = sp.iloc[0]
    # product: 400 against an average month of 100 over the 12 before -> 300 extra
    assert r["excess_over_average"] == pytest.approx(300)
    # ACME BANK 300 against its own 100 -> 200; the newcomer 100 against 0 -> 100
    assert r["top_company"] == "ACME BANK" and r["top_company_share"] == pytest.approx(2 / 3)
    assert r["second_company"] == "Newcomer LLC" and r["second_company_share"] == pytest.approx(1 / 3)


def test_toy_fiscal_years_set_spikes_to_baseline(toy):
    fy = M.fiscal_years(toy).set_index(["current_product", "fiscal_year"])
    # FY2021 = Oct 2020 .. Sep 2021: 3 x 100, Jan 400, Feb 100, Mar 200, Apr-Jun 3 x 100, Jul-Sep 3 x 400
    row = fy.loc[(T.MORTGAGE, 2021)]
    assert row["complaints"] == 300 + 400 + 100 + 200 + 300 + 1200
    assert row["adjusted"] == row["complaints"] - 400 + 100
    assert row["spike_months"] == 1


# ---------------------------------------------------------------- the committed data

@pytest.fixture(scope="module")
def con():
    return M.connect()


def test_every_pair_maps_to_a_current_product(con):
    pm = M.product_map(con)
    assert set(pm["current_product"]) == set(T.CURRENT_PRODUCTS)
    assert pm["complaints"].sum() == 19_397_176
    assert not pm.duplicated(["product", "sub_product"]).any()
    snap_products = set(con.execute("SELECT DISTINCT product FROM complaints").df()["product"])
    assert snap_products == set(T.CURRENT_PRODUCTS) - {T.CREDIT_REPORTING}
    assert con.execute("SELECT sum(complaints) FROM history").fetchone()[0] == 19_397_176


def test_map_keeps_fiscal_year_totals(con):
    fy = M.fiscal_years(con).groupby("fiscal_year")["complaints"].sum()
    hist = P.history(con).set_index("fiscal_year")["complaints"]
    assert fy.to_dict() == hist[hist.index <= 2026].to_dict()


def test_split_products_go_to_both_sides(con):
    pm = M.product_map(con)
    cc = pm[pm["product"] == "Credit card or prepaid card"].groupby("current_product")["complaints"].sum()
    assert cc.to_dict() == {T.CREDIT_CARD: 186_789, T.PREPAID: 19_567}


def test_company_names(con):
    snap = con.execute("SELECT count(DISTINCT company) - count(DISTINCT company_merged) FROM complaints_flagged")
    assert snap.fetchone()[0] == 4
    hist = con.execute("SELECT count(*) - count(DISTINCT company_merged) FROM company_names").fetchone()[0]
    assert hist == 12
    # the merged name is the spelling with the most complaints
    assert con.execute("SELECT company_merged FROM company_names WHERE company = 'ONEMAIN FINANCE CORPORATION'"
                       ).fetchone()[0] == "OneMain Finance Corporation"


def test_spikes(con):
    sp = M.spikes(con)
    assert len(sp) == 24
    assert not sp["month"].between("2025-10", "2026-09").any()
    jan = sp.set_index(["current_product", "month"]).loc[(T.MONEY, "2025-01")]
    assert (jan["complaints"], jan["baseline"]) == (49_743, 2_737.5)
    assert jan["top_company"] == "Block, Inc." and jan["second_company"] == "Early Warning Services, LLC"
    assert len(M.recent_flags(con)) == 0


def test_spike_company_excess_adds_up(con):
    comp = M.spike_companies(con)
    pmo = M.product_months(con).set_index(["current_product", "month"])["complaints"]
    for (prod, m), g in comp.groupby(["current_product", "month"]):
        prior = [p.strftime("%Y-%m") for p in pd.period_range(end=pd.Period(m, "M") - 1, periods=12, freq="M")]
        avg = sum(pmo.get((prod, x), 0) for x in prior) / 12
        assert g["excess"].sum() == pytest.approx(pmo[(prod, m)] - avg), (prod, m)
        assert g["complaints"].sum() == pmo[(prod, m)]


def test_change_by_company_adds_up(con):
    chg = M.change_by_company(con)
    pmo = M.product_months(con)
    keep = pmo[pmo["fiscal_year"].isin([2025, 2026]) & pmo["status"].ne("spike")]
    per_month = keep.groupby(["current_product", "fiscal_year"])["complaints"].mean().unstack()
    got = chg.groupby("current_product")[["per_month_2025", "per_month_2026"]].sum()
    for prod in per_month.index:
        assert got.loc[prod, "per_month_2025"] == pytest.approx(per_month.loc[prod, 2025])
        assert got.loc[prod, "per_month_2026"] == pytest.approx(per_month.loc[prod, 2026])
    assert chg.groupby("current_product")["months_2025"].first()[T.MONEY] == 10


def test_weekly_check(con):
    wk = M.weekly(con)
    # 51 full weeks, less 8 at each end without a full window, for 10 products
    assert len(wk) == 10 * (51 - 16)
    assert not wk["spike"].any()
    assert wk["complaints"].sum() < 658_443


def test_sensitivity_finds_nothing_in_fy2026(con):
    sens = M.sensitivity(con)
    assert (sens["in_fy2026"] == 0).all()
    assert sens.set_index(["ratio", "min_excess"]).loc[(1.5, 250), "spike_months"] == 24


def test_repeats_match_part1(con):
    q = P.quality_checks(con).set_index("check_id")["complaints"]
    rob = M.robustness(con)
    p = rob["products"]
    assert p["complaints"].sum() - p["complaints_no_repeats"].sum() == q[19] == 17_349
    assert rob["merged_complaints"] == 392
    assert rob["top10_same_set"] and rob["top_issue_same"]


def test_issue_mix_against_pandas(con):
    df = con.execute("SELECT product, issue FROM complaints").df()
    counts = df.groupby(["product", "issue"]).size()
    mix = M.issue_mix(con).set_index(["product", "issue"])
    assert mix["complaints"].to_dict() == counts.to_dict()
    assert mix.groupby("product")["share"].sum().round(9).eq(1).all()


def test_report_regenerates_byte_for_byte(tmp_path):
    sources_report.write(tmp_path)
    produced = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    assert len(produced) == 1 + 8 + 4
    for rel in produced:
        assert (tmp_path / rel).read_bytes() == (RESULTS / rel).read_bytes(), rel


def test_every_committed_result_comes_from_a_report(tmp_path):
    """Each file in results/ is written by exactly one report, and each report links its own charts."""
    from scripts import monitor_report, profile_report, response_report
    made = {}
    for name, mod, report in (("p1", profile_report, "PROFILE.md"), ("p2", sources_report, sources_report.REPORT),
                              ("p3", response_report, response_report.REPORT),
                              ("p4", monitor_report, monitor_report.REPORT)):
        d = tmp_path / name
        mod.write(d)
        made[name] = {p.relative_to(d) for p in d.rglob("*") if p.is_file()}
        links = set(re.findall(r"\]\((charts/[^)]+\.png)\)", (d / report).read_text()))
        assert links == {str(p) for p in made[name] if p.suffix == ".png"}
    names = sorted(made)
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            assert not made[x] & made[y], (x, y)
    committed = {p.relative_to(RESULTS) for p in RESULTS.rglob("*") if p.is_file()}
    assert committed == set().union(*made.values())
