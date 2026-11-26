"""Part 3: how companies respond.

First on a hand-made snapshot where every expected value is worked out by hand, then on the
committed data (against an independent pandas version of the peer comparison).
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
import pytest

from complaints import build, load, response as R, source
from scripts import response_report
from tests.conftest import bulk_row, write_bulk

RESULTS = source.ROOT / "results"
DC = "Debt collection"
A, B = "Attempts to collect debt not owed", "Written notification about debt"


# ---------------------------------------------------------------- hand-made snapshot

def _toy_rows() -> list[dict]:
    rows, cid = [], iter(range(1, 1000))

    def add(company, issue, response, k, timely="Yes", received="2026-01-15"):
        for _ in range(k):
            rows.append(bulk_row(next(cid), product=DC, sub_product="Other debt", issue=issue, sub_issue="",
                                 company=company, response=response, timely=timely, received=received,
                                 # every complaint distinct, so none is a repeat
                                 zip_code=f"{next(cid):05d}"))
    # X: 10 final responses on issue A: 1 monetary, 4 non-monetary, 3 explanation, 1 explanation closed
    # late, 1 untimely response; plus 1 still in progress (left out of everything).
    add("X LLC", A, "Closed with monetary relief", 1)
    add("X LLC", A, "Closed with non-monetary relief", 4)
    add("X LLC", A, "Closed with explanation", 3)
    add("X LLC", A, "Closed with explanation", 1, timely="No")
    add("X LLC", A, "Untimely response", 1, timely="No")
    add("X LLC", A, "In progress", 1)
    # Y: 10 on issue A (1 relief) and 20 on issue B (no relief). Z: 40 on issue A (8 relief).
    add("Y INC", A, "Closed with non-monetary relief", 1)
    add("Y INC", A, "Closed with explanation", 9)
    add("Y INC", B, "Closed with explanation", 20)
    add("Z CORP", A, "Closed with non-monetary relief", 8, received="2026-05-15")
    add("Z CORP", A, "Closed with explanation", 32, received="2025-11-15")
    return rows


@pytest.fixture(scope="module")
def toy(tmp_path_factory):
    d = tmp_path_factory.mktemp("toy3")
    csv_path = write_bulk(d / "c.csv", _toy_rows())
    build.build(csv_path, d / "s.parquet", d / "m.csv")
    hist = pd.DataFrame({"month": ["2026-01"] * 3, "product": [DC] * 3, "sub_product": ["Other debt"] * 3,
                         "company": ["X LLC", "Y INC", "Z CORP"], "complaints": [11, 30, 40]})
    comp = d / "company.parquet"
    duckdb.register("h", hist)
    duckdb.execute(f"COPY (SELECT month, product, sub_product, company, CAST(complaints AS BIGINT) AS complaints "
                   f"FROM h) TO '{comp}' (FORMAT parquet)")
    duckdb.unregister("h")
    con = load.connect(d / "s.parquet", d / "m.csv", comp)
    R.prepare(con)
    return con


def test_toy_responses_view(toy):
    t = R.totals(toy)
    assert t["final_responses"] == 80                      # the in-progress complaint is left out
    assert t["relief"] == 1 + 4 + 1 + 8
    assert t["monetary"] == 1
    assert t["late"] == 2 and t["untimely_response"] == 1 and t["closed_late"] == 1
    bp = R.by_product(toy).set_index("product").loc[DC]
    assert bp["complaints"] == 81 and bp["in_progress"] == 1 and bp["final_responses"] == 80
    assert bp["relief_rate"] == pytest.approx(14 / 80)
    assert bp["explanation"] == 3 + 1 + 9 + 20 + 32


def test_toy_expected_leaves_the_company_out_and_falls_back(toy):
    ce = R.company_expected(toy, min_responses=1).set_index("company")
    x, y, z = ce.loc["X LLC"], ce.loc["Y INC"], ce.loc["Z CORP"]
    # X on issue A: peers Y (10) + Z (40) = 50 >= 30, with 1 + 8 relief -> 0.18
    assert x["final_responses"] == 10 and x["observed"] == 5
    assert x["expected"] == pytest.approx(10 * 0.18)
    assert x["variance"] == pytest.approx(10 * 0.18 * 0.82)
    assert np.isnan(x["fallback_responses"])
    # Y on A: peers X + Z = 50, 13 relief -> 0.26. On B: no peers -> the product without Y: X + Z, 13 / 50.
    assert y["expected"] == pytest.approx(10 * 0.26 + 20 * 0.26)
    assert y["fallback_responses"] == 20
    # Z on A: peers X + Y on A = 20 < 30 -> the product without Z: X 10 (5) + Y 30 (1) -> 6 / 40
    assert z["expected"] == pytest.approx(40 * 0.15)
    assert z["variance"] == pytest.approx(40 * 0.15 * 0.85)
    assert z["fallback_responses"] == 40
    assert z["z"] == pytest.approx((8 - 6) / np.sqrt(5.1))
    assert np.allclose(ce["overall_rate"], 14 / 80)
    assert x["raw_difference"] == pytest.approx(0.5 - 14 / 80)
    # z = (5 - 1.8) / sqrt(1.476) = 2.63: outside the 95% limits, inside the 99.8% ones
    assert x["z"] == pytest.approx((5 - 1.8) / np.sqrt(1.476))
    assert x["verdict"] == "within" and x["outside_95"]


def test_toy_monetary_metric(toy):
    cm = R.company_expected(toy, "monetary", min_responses=1).set_index("company")
    assert cm.loc["X LLC", "observed"] == 1 and cm.loc["X LLC", "expected"] == 0
    with pytest.raises(ValueError):
        R.company_expected(toy, "late")


def test_toy_halves_and_late(toy):
    h = R.halves(toy).set_index("company")
    assert h.loc["Z CORP", "n1"] == 32 and h.loc["Z CORP", "relief1"] == 0
    assert h.loc["Z CORP", "n2"] == 8 and h.loc["Z CORP", "relief2"] == 8
    r1, r2 = R.half_rates(R.halves(toy))
    assert h["contribution"].sum() == pytest.approx(r2 - r1)
    lt = R.late_by_company(toy)
    assert lt.iloc[0]["company"] == "X LLC" and lt.iloc[0]["late"] == 2
    assert lt.iloc[0]["untimely_response"] == 1 and lt.iloc[0]["closed_late"] == 1
    ls = R.late_summary(lt)
    assert ls["late"] == 2 and ls["companies_with_late"] == 1 and ls["companies_for_half"] == 1


def test_toy_verdicts_use_the_998_limit(toy):
    ce = R.company_expected(toy, min_responses=1).set_index("company")
    for c, r in ce.iterrows():
        expect = "above" if r["z"] > 3.090232 else "below" if r["z"] < -3.090232 else "within"
        assert r["verdict"] == expect, c
        assert r["outside_95"] == (abs(r["z"]) > 1.959964)


def test_min_responses_filter(toy):
    assert set(R.company_expected(toy, min_responses=11)["company"]) == {"Y INC", "Z CORP"}


# ---------------------------------------------------------------- committed data

@pytest.fixture(scope="module")
def con():
    return R.connect()


@pytest.fixture(scope="module")
def resp(con):
    return con.execute("SELECT company_merged AS company, product, issue, relief, monetary, late, first_half, "
                       "company_response, is_repeat FROM responses").df()


def _pandas_expected(r: pd.DataFrame, metric: str) -> pd.DataFrame:
    """The peer comparison written again in pandas, as plainly as possible."""
    cell = r.groupby(["company", "product", "issue"], as_index=False).agg(n=(metric, "size"), o=(metric, "sum"))
    ca = cell.groupby(["product", "issue"], as_index=False)[["n", "o"]].sum()
    pa = cell.groupby("product", as_index=False)[["n", "o"]].sum()
    pc = cell.groupby(["company", "product"], as_index=False)[["n", "o"]].sum()
    m = (cell.merge(ca, on=["product", "issue"], suffixes=("", "_cell"))
         .merge(pa, on="product", suffixes=("", "_prod"))
         .merge(pc, on=["company", "product"], suffixes=("", "_pc")))
    peer_n, peer_o = m["n_cell"] - m["n"], m["o_cell"] - m["o"]
    pp_n, pp_o = m["n_prod"] - m["n_pc"], m["o_prod"] - m["o_pc"]
    assert (pp_n > 0).all()          # on this data the all-products fallback is never needed
    m["p"] = np.where(peer_n >= R.MIN_PEER, peer_o / peer_n.where(peer_n > 0, 1), pp_o / pp_n)
    g = m.assign(e=m["n"] * m["p"], v=m["n"] * m["p"] * (1 - m["p"])).groupby("company")
    return pd.DataFrame({"n": g["n"].sum(), "o": g["o"].sum(), "e": g["e"].sum(), "v": g["v"].sum()})


@pytest.mark.parametrize("metric", ["relief", "monetary"])
def test_expected_against_pandas(con, resp, metric):
    ce = R.company_expected(con, metric).set_index("company")
    pdx = _pandas_expected(resp, metric)
    pdx = pdx[pdx["n"] >= R.MIN_RESPONSES]
    assert set(ce.index) == set(pdx.index)
    pdx = pdx.loc[ce.index]
    assert (ce["final_responses"].values == pdx["n"].values).all()
    assert (ce["observed"].values == pdx["o"].values).all()
    np.testing.assert_allclose(ce["expected"].values, pdx["e"].values, rtol=1e-9)
    np.testing.assert_allclose(ce["variance"].values, pdx["v"].values, rtol=1e-9)


def test_responses_against_part1(con, resp):
    t = R.totals(con)
    assert t["final_responses"] == 658_443 - 1_743
    assert (t["late"], t["untimely_response"], t["closed_late"]) == (24_673, 15_098, 9_575)
    assert t["relief"] == int((resp["company_response"].str.endswith("relief")).sum())
    bp = R.by_product(con)
    assert bp["complaints"].sum() == 658_443 and bp["in_progress"].sum() == 1_743
    parts = bp[["monetary_relief", "non_monetary_relief", "explanation", "untimely_response"]].sum(axis=1)
    assert (parts == bp["final_responses"]).all()      # the four final outcomes cover every final response
    # the raw benchmark is the rate over every company, not only those large enough to be compared
    ce = R.company_expected(con)
    assert np.allclose(ce["overall_rate"], t["relief_rate"])
    assert np.allclose(R.company_expected(con, min_responses=1)["overall_rate"], t["relief_rate"])


def test_halves_contributions_add_up(con, resp):
    h = R.halves(con)
    r1, r2 = R.half_rates(h)
    assert h["contribution"].sum() == pytest.approx(r2 - r1, abs=1e-12)
    assert r1 == pytest.approx(resp.loc[resp["first_half"], "relief"].mean())
    assert r2 == pytest.approx(resp.loc[~resp["first_half"], "relief"].mean())


def test_by_month_without_a_company(con, resp):
    who = R.halves(con).iloc[0]["company"]
    m = R.by_month(con, (who,))
    rest = resp[resp["company"] != who]
    assert m["final_responses"].sum() == len(rest)
    assert m["relief"].sum() == rest["relief"].sum()
    # expected rates average back to the actual overall rate (the cell rates come from the same rows)
    assert np.average(m["expected_rate"], weights=m["final_responses"]) == pytest.approx(rest["relief"].mean())


def test_late_concentration(con):
    lt = R.late_by_company(con)
    assert lt["late"].is_monotonic_decreasing
    assert lt["late"].sum() == 24_673 and (lt["untimely_response"] + lt["closed_late"] == lt["late"]).all()
    s = R.late_summary(lt)
    k = s["companies_for_half"]
    assert lt["late"].head(k).sum() >= 0.5 * lt["late"].sum() > lt["late"].head(k - 1).sum()


def test_repeats_check_matches_a_direct_rerun(con):
    rc = R.repeats_check(con)
    b = R.company_expected(con, where="NOT is_repeat")
    assert rc["companies_nr"] == len(b)
    assert rc["same_verdict"] + len(rc["changed"]) == rc["both"]


def test_report_regenerates_byte_for_byte(tmp_path):
    response_report.write(tmp_path)
    produced = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    assert len(produced) == 1 + 7 + 4
    for rel in produced:
        assert (tmp_path / rel).read_bytes() == (RESULTS / rel).read_bytes(), rel
