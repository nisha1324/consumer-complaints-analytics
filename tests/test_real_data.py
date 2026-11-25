"""Checks on the committed snapshot and on the Part 1 outputs made from it."""
from __future__ import annotations

import json
import re

import pandas as pd
import pytest

from complaints import load, profile as P, source
from scripts import download_data, profile_report

RESULTS = source.ROOT / "results"


@pytest.fixture(scope="module")
def con():
    return load.connect()


@pytest.fixture(scope="module")
def df(con):
    return con.execute("SELECT * FROM complaints").df()


@pytest.fixture(scope="module")
def manifest():
    return json.loads(source.MANIFEST_PATH.read_text())


def test_committed_files_match_pinned_hashes():
    assert download_data.check() == 0
    assert source.sha256_file(source.SNAPSHOT_PATH) == source.SNAPSHOT_SHA256
    assert source.sha256_file(source.MONTHLY_PATH) == source.MONTHLY_SHA256


def test_manifest_agrees_with_files(manifest, df, con):
    assert manifest["snapshot_sha256"] == source.SNAPSHOT_SHA256
    assert manifest["monthly_sha256"] == source.MONTHLY_SHA256
    assert manifest["snapshot_rows"] == len(df) == 658_443
    monthly = con.execute("SELECT * FROM monthly").df()
    assert manifest["monthly_rows"] == len(monthly)
    assert manifest["monthly_total"] == monthly["complaints"].sum() == manifest["bulk_rows"]
    assert manifest["window"] == {"start": source.WINDOW_START, "end": source.WINDOW_END}
    assert manifest["excluded_products"] == list(source.CREDIT_REPORTING_PRODUCTS)


def test_snapshot_shape(df):
    assert list(df.columns) == list(P.COLUMNS)
    assert df["complaint_id"].is_monotonic_increasing and df["complaint_id"].is_unique
    assert df["date_received"].min() == pd.Timestamp(source.WINDOW_START)
    assert df["date_received"].max() == pd.Timestamp(source.WINDOW_END)
    assert not df["product"].isin(source.CREDIT_REPORTING_PRODUCTS).any()
    assert not df["product"].str.startswith("Credit reporting").any()
    assert df["product"].nunique() == 10


def test_the_two_committed_files_agree(con, df):
    """FY2026 non-credit-reporting complaints in the monthly history = rows in the snapshot, product by product."""
    hist = con.execute("""
        SELECT product, sum(complaints) AS n FROM monthly
        WHERE month BETWEEN '2025-10' AND '2026-09' AND NOT product ILIKE 'Credit reporting%'
        GROUP BY product
    """).df().set_index("product")["n"].sort_index()
    snap = df.groupby("product").size().sort_index()
    assert hist.to_dict() == snap.to_dict()
    fy = P.history(con).set_index("fiscal_year")
    assert fy.loc[2026, "other_products"] == len(df)


def test_quality_checks_against_pandas(con, df):
    q = P.quality_checks(con).set_index("check_id")["complaints"]
    key = [c for c in P.COLUMNS if c != "complaint_id"]
    assert q[19] == df.duplicated(subset=key).sum()
    lag = (df["date_sent_to_company"] - df["date_received"]).dt.days
    assert q[4] == (lag > 14).sum()
    assert q[6] == (df["company_response"] == "In progress").sum()
    assert q[7] + q[8] == df["timely_response"].eq(False).sum()
    assert q[10] == df["state"].isna().sum()
    assert q[12] == df["zip_code"].str.fullmatch(r"\d{3}XX").sum()
    assert q[13] == (df["zip_code"] == "XXXXX").sum()
    with_sub = set(map(tuple, df.loc[df["sub_issue"].notna(), ["product", "issue"]].drop_duplicates().values))
    missing = df[df["sub_issue"].isna()]
    has = missing[["product", "issue"]].apply(tuple, axis=1).isin(with_sub)
    assert (q[16], q[17]) == (has.eq(False).sum(), has.sum())
    assert P.repeats_by_product(con)["repeats"].sum() == q[19]


def test_quality_check_sql_uses_the_window():
    sql = load.sql("quality_checks")
    assert f"DATE '{source.WINDOW_START}' AND DATE '{source.WINDOW_END}'" in sql


@pytest.mark.parametrize("check_id", [1, 2, 3, 5, 9, 15, 17, 18])
def test_checks_whose_note_says_none(con, check_id):
    """The notes for these checks ("Each row is one complaint", "No true gaps", ...) assume zero."""
    q = P.quality_checks(con).set_index("check_id")["complaints"]
    assert q[check_id] == 0


def test_state_note_names_the_only_odd_value(df):
    odd = df.loc[df["state"].notna() & df["state"].str.fullmatch(r"[A-Z]{2}", na=False).eq(False), "state"].unique().tolist()
    assert odd == ["UNITED STATES MINOR OUTLYING ISLANDS"]
    assert "UNITED STATES MINOR OUTLYING ISLANDS" in profile_report.CHECK_NOTES[11]


def test_concentration_against_pandas(con, df):
    counts = df.groupby("company").size().sort_values(ascending=False)
    conc = P.concentration(con)
    assert conc["complaints"].tolist() == counts.tolist()
    s = P.concentration_summary(conc)
    cum = counts.cumsum() / counts.sum()
    assert s["companies_for_half"] == int((cum < 0.5).sum() + 1) == 22
    assert s["companies_for_80"] == 109
    assert s["top10_share"] == pytest.approx(counts.head(10).sum() / len(df))
    assert s["single_complaint_companies"] == (counts == 1).sum() == 1104


def test_product_mix_against_pandas(con, df):
    mix = P.product_mix(con).set_index("product")
    assert mix["complaints"].to_dict() == df.groupby("product").size().to_dict()
    assert mix["companies"].to_dict() == df.groupby("product")["company"].nunique().to_dict()
    assert mix["share"].sum() == pytest.approx(1.0)


def test_surge_is_january_2025_and_outside_the_window(con):
    s = P.surge_month(con)
    assert s["month"] == "2025-01"
    assert s["month"] < source.WINDOW_START[:7]
    jump = s["complaints"] - s["prev_complaints"]
    assert s["jump_share"] == pytest.approx((s["mt"] - s["mt_prev"] + s["bank"] - s["bank_prev"]) / jump)
    assert s["jump_share"] > 0.5            # "most of the increase" in the report


def test_profile_regenerates_byte_for_byte(tmp_path):
    profile_report.write(tmp_path)
    produced = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    committed = sorted(p.relative_to(RESULTS) for p in RESULTS.rglob("*") if p.is_file()
                       and (p.name == "PROFILE.md" or p.suffix in (".csv", ".png")))
    assert produced == committed
    for rel in produced:
        assert (tmp_path / rel).read_bytes() == (RESULTS / rel).read_bytes(), rel


def test_profile_links_every_chart():
    text = (RESULTS / "PROFILE.md").read_text()
    links = re.findall(r"\]\((charts/[^)]+\.png)\)", text)
    charts = sorted(f"charts/{p.name}" for p in (RESULTS / "charts").glob("*.png"))
    assert sorted(set(links)) == charts
