"""Every figure the README states about Part 1, re-derived from the committed data."""
from __future__ import annotations

import json
import re

import pytest

from complaints import load, profile as P, source

README = (source.ROOT / "README.md").read_text()


def n(x) -> str:
    return f"{int(x):,}"


def pct(x, nd=1) -> str:
    return f"{100 * x:.{nd}f}%"


@pytest.fixture(scope="module")
def facts():
    con = load.connect()
    hist = P.history(con).set_index("fiscal_year")
    mix = P.product_mix(con).set_index("product")
    summ = P.concentration_summary(P.concentration(con))
    q = P.quality_checks(con).set_index("check_id")["complaints"]
    reps = P.repeats_by_product(con).set_index("product")["repeats"]
    names = P.name_collisions(con)
    sep = P.response_by_month(con).set_index("month").loc["2026-09"]
    manifest = json.loads(source.MANIFEST_PATH.read_text())
    return dict(con=con, hist=hist, mix=mix, summ=summ, q=q, reps=reps, names=names, sep=sep,
                manifest=manifest, surge=P.surge_month(con))


def has(*fragments):
    for f in fragments:
        assert f in README, f


def test_source_and_snapshot(facts):
    m = facts["manifest"]
    has(f"{n(m['bulk_rows'])} complaints from December 2011 to 23 November 2026",
        f"**{n(m['snapshot_rows'])} complaints**")
    assert m["bulk_zip_bytes"] // 1_000_000 == 371
    assert round(source.SNAPSHOT_PATH.stat().st_size / 1e6, 1) == 5.8
    assert round(source.COMPANY_MONTHLY_PATH.stat().st_size / 1e6, 1) == 1.4
    has(f"for the whole history ({n(m['company_monthly_rows'])} rows)")
    assert "dated 24 November 2026" in README and m["bulk_last_modified"].startswith("Tue, 24 Nov 2026")


def test_history(facts):
    h = facts["hist"]
    f19, f26 = h.loc[2019], h.loc[2026]
    has(f"grew {f26['complaints'] / f19['complaints']:.0f}-fold in seven years",
        f"from {n(f19['complaints'])} in FY2019 to {n(f26['complaints'])} in FY2026",
        f"from {pct(f19['credit_reporting_share'])} to {pct(f26['credit_reporting_share'])} of them",
        f"from {n(f19['other_products'])} to {n(f26['other_products'])} "
        f"({f26['other_products'] / f19['other_products']:.1f}-fold)",
        f"It was {pct(f26['credit_reporting_share'])} of all complaints in FY2026 "
        f"({f26['credit_reporting'] / 1e6:.1f} million)")


def test_surge(facts):
    s = facts["surge"]
    has(f"{s['month_name']} had {n(s['complaints'])} complaints",
        f"make up {pct(s['jump_share'], 0)} of the increase")
    assert round(s["complaints"] / s["prev_complaints"]) == 3      # "three times the month before"


def test_products_and_companies(facts):
    mix, summ = facts["mix"], facts["summ"]
    dc = mix.loc["Debt collection"]
    has(f"({n(dc['complaints'])} complaints, {pct(dc['share'])})",
        f"credit cards ({pct(mix.loc['Credit card', 'share'])})",
        f"checking or savings accounts ({pct(mix.loc['Checking or savings account', 'share'])})",
        f"draw {pct(summ['top10_share'])} of complaints and {summ['companies_for_half']} companies draw half",
        f"{n(summ['single_complaint_companies'])} of {n(summ['companies'])} companies have a single complaint")
    assert mix.index[0] == "Debt collection" and dc["share"] < 0.5          # "half": 49.3%
    assert list(mix.index[1:3]) == ["Credit card", "Checking or savings account"]


def test_trap_table(facts):
    q, sep, reps, names = facts["q"], facts["sep"], facts["reps"], facts["names"]
    has(f"{n(q[6])} still in progress, {n(sep['in_progress'])} of them from September 2026",
        f"{n(q[7])} \"Untimely response\" + {n(q[8])} closed late = {n(q[7] + q[8])} "
        f"({pct((q[7] + q[8]) / 658_443)})",
        f"{n(q[19])} ({pct(q[19] / 658_443)}), {pct(reps['Debt collection'] / q[19], 0)} of them in debt collection",
        f"{names['name_key'].nunique()} companies, {n(q[20])} complaints",
        f"{n(q[12])} show 3 digits, {n(q[13])} none")
    assert q[1] == q[3] == q[5] == 0     # "No duplicate IDs, no dates out of order and no timeliness flag missing"
    assert "21 data-quality checks" in README and len(P.quality_checks(facts["con"])) == 21


def test_disk_space_claim(facts):
    m = facts["manifest"]
    unzipped = 5_886_596_396   # size of complaints.csv inside the zip, from the rebuild on 2026-11-25
    assert round((m["bulk_zip_bytes"] + unzipped) / 1e9, 1) == 6.3
    assert "about 6.3 GB of disk" in README


def test_links_resolve():
    for target in re.findall(r"\]\((?!https?://|#)([^)]+)\)", README):
        assert (source.ROOT / target).exists(), target


def test_status_and_chart_links():
    assert "**Status: in progress. Part 1 of 5" in README
    charts = re.findall(r"\(results/charts/([^)]+\.png)\)", README)
    assert charts == ["01_history_by_month.png", "02_fy2026_by_product.png"]
