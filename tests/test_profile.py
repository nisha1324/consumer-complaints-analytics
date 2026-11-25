"""The profile queries on a toy snapshot, with every expected count worked out by hand."""
from __future__ import annotations

import pandas as pd
import pytest

from complaints import build, load, profile as P
from tests.conftest import bulk_row, write_bulk


def _toy_rows():
    r = []
    # 1-3: identical except the ID -> 2 repeats
    for cid in (1, 2, 3):
        r.append(bulk_row(cid, received="2026-01-05", product="Debt collection", company="Big Collector",
                          issue="Attempts to collect debt not owed", sub_issue="Debt is not yours"))
    # 4: same as 1-3 but another ZIP -> not a repeat
    r.append(bulk_row(4, received="2026-01-05", product="Debt collection", company="Big Collector",
                      issue="Attempts to collect debt not owed", sub_issue="Debt is not yours", zip_code="750XX"))
    # 5: issue that never has a sub-issue
    r.append(bulk_row(5, product="Mortgage", issue="Struggling to pay mortgage", sub_issue="",
                      company="First Tech FCU"))
    # 6: same name, different case and punctuation; a ZIP in no published format
    r.append(bulk_row(6, company="FIRST TECH, FCU", zip_code="750X"))
    # 7: in progress, sent 20 days later
    r.append(bulk_row(7, received="2026-09-01", sent="2026-09-21", response="In progress"))
    # 8: untimely response
    r.append(bulk_row(8, response="Untimely response", timely="No", state="", zip_code=""))
    # 9: closed but late; state as a full name
    r.append(bulk_row(9, response="Closed with monetary relief", timely="No",
                      state="UNITED STATES MINOR OUTLYING ISLANDS", zip_code="XXXXX"))
    # 10: issue that has a sub-issue elsewhere (row 1) but is missing here
    r.append(bulk_row(10, product="Debt collection", company="Small Collector",
                      issue="Attempts to collect debt not owed", sub_issue="",
                      tags="Older American, Servicemember"))
    return r


_SNAP: list = []


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    d = tmp_path_factory.mktemp("toy")
    csv_path = write_bulk(d / "complaints.csv", _toy_rows())
    build.build(csv_path, d / "snap.parquet", d / "monthly.csv")
    _SNAP[:] = [d / "snap.parquet"]
    return load.connect(d / "snap.parquet", d / "monthly.csv")


def test_quality_checks_by_hand(con):
    q = P.quality_checks(con).set_index("check_id")["complaints"].to_dict()
    expected = {1: 0, 2: 0, 3: 0, 4: 1, 5: 0, 6: 1, 7: 1, 8: 1, 9: 0, 10: 1, 11: 1, 12: 1, 13: 1, 14: 1,
                15: 1, 16: 1, 17: 1, 18: 0, 19: 2, 20: 2, 21: 1}
    assert q == expected


def test_quality_check_shares(con):
    q = P.quality_checks(con)
    assert (q["share"] == q["complaints"] / 10).all()


def test_repeats_by_product_agrees_with_check_19(con):
    reps = P.repeats_by_product(con)
    assert reps["repeats"].sum() == 2
    assert reps.set_index("product").loc["Debt collection", "repeats"] == 2
    assert reps["complaints"].sum() == 10


def test_name_collisions(con):
    names = P.name_collisions(con)
    assert sorted(names["company"]) == ["FIRST TECH, FCU", "First Tech FCU"]
    assert names["name_key"].nunique() == 1


def test_concentration(con):
    conc = P.concentration(con)
    # Big Collector 4 (rows 1-4), ACME BANK 3 (7-9), then three companies with 1, ties broken by name
    assert conc["company"].tolist() == ["Big Collector", "ACME BANK", "FIRST TECH, FCU", "First Tech FCU",
                                        "Small Collector"]
    assert conc["complaints"].tolist() == [4, 3, 1, 1, 1]
    assert conc["cumulative_share"].tolist() == pytest.approx([0.4, 0.7, 0.8, 0.9, 1.0])
    s = P.concentration_summary(conc)
    assert s["companies"] == 5
    assert s["companies_for_half"] == 2        # 40% after one, 70% after two
    assert s["companies_for_80"] == 3          # exactly 80% after three
    assert s["single_complaint_companies"] == 3
    assert s["top10_share"] == pytest.approx(1.0)


def test_concentration_summary_thresholds():
    conc = pd.DataFrame({"rank": [1, 2, 3, 4], "complaints": [5, 3, 1, 1],
                         "cumulative_share": [0.5, 0.8, 0.9, 1.0]})
    s = P.concentration_summary(conc)
    assert s["companies_for_half"] == 1   # the first company reaches exactly 50%
    assert s["companies_for_80"] == 2
    assert s["top10_share"] == 1.0
    assert s["single_complaint_companies"] == 2


def test_sending_lag(con):
    lag = P.sending_lag(con)
    assert lag["max"] == 20
    assert lag["median"] == 0
    assert lag["same_day_share"] == pytest.approx(0.9)


def test_column_profile(con):
    cp = P.column_profile(con).set_index("column_name")
    assert list(cp.index) == list(P.COLUMNS)
    assert cp.loc["complaint_id", "distinct_values"] == 10
    assert cp.loc["state", "filled"] == 9
    assert cp.loc["sub_issue", "filled"] == 8
    assert cp.loc["company", "most_common"] == "Big Collector"
    assert cp.loc["company", "most_common_complaints"] == 4
    assert cp.loc["product", "most_common"] == "Debt collection"     # 5 against 4 credit card
    assert cp.loc["tags", "filled"] == 1


def test_response_by_month(con):
    r = P.response_by_month(con).set_index("month")
    assert r["complaints"].sum() == 10
    assert r.loc["2026-09", "in_progress"] == 1
    assert r["not_timely"].sum() == 2
    assert r["untimely_response"].sum() == 1
    assert r["monetary_relief"].sum() == 1


def test_old_in_progress_cut_off(con):
    assert P.old_in_progress(con).empty                       # row 7 is from September
    assert P.old_in_progress(con, before="2026-10-01")["complaints"].tolist() == [1]


def test_history(con):
    h = P.history(con)
    assert h["complaints"].sum() == 10
    assert h["fiscal_year"].tolist() == [2026]
    assert (h["credit_reporting"] == 0).all()
    assert (h["other_products"] == h["complaints"]).all()


def test_fiscal_year_and_surge(tmp_path, con):
    monthly = pd.DataFrame({
        "month": ["2024-09", "2024-10", "2024-11", "2024-12", "2025-01", "2025-02", "2025-02"],
        "product": ["Mortgage", "Mortgage", "Money transfers", "Credit reporting", "Mortgage",
                    "Money transfer, virtual currency, or money service", "Checking or savings account"],
        "complaints": [5, 7, 50, 900, 6, 4, 3],
    })
    path = tmp_path / "monthly.csv"
    monthly.to_csv(path, index=False)
    c2 = load.connect(_SNAP[0], path)
    h = P.history(c2).set_index("fiscal_year")
    assert h.loc[2024, "complaints"] == 5                  # September 2024 is FY2024
    assert h.loc[2025, "complaints"] == 7 + 50 + 900 + 6 + 4 + 3
    assert h.loc[2025, "credit_reporting"] == 900
    assert h.loc[2025, "other_products"] == 70
    s = P.surge_month(c2)
    assert s["month"] == "2024-11" and s["month_name"] == "November 2024"
    assert (s["complaints"], s["prev_complaints"], s["next_complaints"]) == (50, 7, 0)
    assert (s["mt"], s["mt_prev"]) == (50, 0)          # "Money transfers" matches "Money transfer%"
    assert (s["bank"], s["bank_prev"]) == (0, 0)
