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
    assert "**Status: in progress. Parts 1 and 2 of 5 are done" in README
    charts = re.findall(r"\(results/charts/([^)]+\.png)\)", README)
    assert charts == ["01_history_by_month.png", "02_fy2026_by_product.png",
                      "05_products_by_month.png", "07_growth_with_and_without_spikes.png"]
    for c in charts:
        assert (source.ROOT / "results" / "charts" / c).exists()


# ---------------------------------------------------------------- Part 2

@pytest.fixture(scope="module")
def part2():
    from complaints import mix as M, taxonomy as T
    con = M.connect()
    pm = M.product_map(con)
    summ = M.map_summary(pm)
    sp = M.spikes(con)
    gr = M.growth(M.fiscal_years(con)).set_index("current_product")
    drv = M.change_drivers(M.change_by_company(con))
    top1 = M.top_issues(M.issue_mix(con), 1).set_index("product")
    rob = M.robustness(con)
    sens = M.sensitivity(con)
    return dict(M=M, T=T, pm=pm, summ=summ, sp=sp, gr=gr, drv=drv, top1=top1, rob=rob, sens=sens)


def signed(x, nd=1):
    return f"{100 * x:+.{nd}f}%".replace("-", "−")


def test_part2_map(part2):
    summ, T = part2["summ"], part2["T"]
    moved = int(summ.loc[summ["product"].isin(T.CURRENT_PRODUCTS), "complaints"].sum())
    total = int(summ["complaints"].sum())
    has(f"{n(total)} complaints move: {n(total - moved)} filed under product names that no longer exist, "
        f"and {n(moved)} filed under a sub-product",
        f"the total stays at {n(part2['pm']['complaints'].sum())}")


def test_part2_spikes(part2):
    sp, T = part2["sp"], part2["T"]
    one = int((sp["top_company_share"] >= 0.5).sum())
    two = int((sp["top_company_share"] + sp["second_company_share"].fillna(0) >= 0.5).sum())
    assert two == len(sp)
    has(f"The history has {len(sp)} spike months. In {one} of them one company makes up half or more",
        f"in all {len(sp)} the two largest companies do")
    jan = sp.set_index(["current_product", "month"]).loc[(T.MONEY, "2025-01")]
    assert (jan["top_company"], jan["second_company"]) == ("Block, Inc.", "Early Warning Services, LLC")
    has(f"made up {pct(jan['top_company_share'] + jan['second_company_share'], 0)} of the money-transfer spike "
        f"({n(jan['complaints'])} complaints against a usual {jan['baseline']:,.0f})")
    wf = sp[(sp["month"] == "2023-01")]
    assert set(wf["top_company"]) == {"WELLS FARGO & COMPANY"}
    assert set(wf["current_product"]) == {T.CHECKING, T.MORTGAGE, T.VEHICLE}
    s = sp.set_index(["current_product", "month"])
    assert s.loc[("Student loan", "2017-01"), "top_company"].startswith("Navient")
    assert s.loc[(T.CREDIT_REPORTING, "2017-09"), "top_company"] == "EQUIFAX, INC."
    assert not sp["month"].between("2025-10", "2026-09").any()
    sens = part2["sens"]
    assert (sens["in_fy2026"] == 0).all() and len(sens) == 4
    has(f"the count of spike months changes ({sens['spike_months'].min()} to {sens['spike_months'].max()})")


def test_part2_growth(part2):
    g, T = part2["gr"], part2["T"]
    mt, ck, st = g.loc[T.MONEY], g.loc[T.CHECKING], g.loc[T.STUDENT]
    has(f"fell {100 * -mt['change_1y']:.1f}% from FY2025 to FY2026",
        f"they rose {100 * mt['change_1y_adjusted']:.1f}%",
        f"Bank accounts go from {signed(ck['change_1y'])} to {signed(ck['change_1y_adjusted'])}",
        f"student loans from {signed(st['change_1y'])} to {signed(st['change_1y_adjusted'])}")
    non_cr = g.drop(index=T.CREDIT_REPORTING)
    grew = int((non_cr["change_1y_adjusted"] > 0).sum())
    has(f"complaints grew in {grew} of {len(non_cr)} products",
        f"payday and personal loans ({signed(g.loc[T.PAYDAY, 'change_1y_adjusted'])})",
        f"mortgages ({signed(g.loc[T.MORTGAGE, 'change_1y_adjusted'])})",
        f"vehicle loans ({signed(g.loc[T.VEHICLE, 'change_1y_adjusted'])})",
        f"Prepaid cards are flat ({signed(g.loc[T.PREPAID, 'change_1y_adjusted'])})")
    top3 = non_cr.sort_values("change_1y_adjusted", ascending=False).index[:3].tolist()
    assert top3 == [T.PAYDAY, T.MORTGAGE, T.VEHICLE]
    drv = part2["drv"]
    assert (drv["companies_up"] > drv["companies_down"]).all()   # "in every product more companies gained"


def test_part2_issues_and_repeats(part2):
    t, T, rob = part2["top1"], part2["T"], part2["rob"]
    for prod, label in ((T.DEBT_COLLECTION, "of debt collection"), (T.CREDIT_CARD, "of credit cards"),
                        (T.CHECKING, "of bank accounts"), (T.MONEY, "of money transfers")):
        has(f"({pct(t.loc[prod, 'share'])} {label})")
    assert t.loc[T.DEBT_COLLECTION, "issue"] == "Attempts to collect debt not owed"
    assert t.loc[T.MONEY, "issue"] == "Fraud or scam"
    p = rob["products"]
    has(f"Without the {n(p['complaints'].sum() - p['complaints_no_repeats'].sum())} repeats")
    t10 = rob["top10"].set_index("company")
    assert tuple(t10.loc["CL Holdings LLC"]) == (1, 2)
    assert tuple(t10.loc["ENCORE CAPITAL GROUP INC."]) == (4, 7)
    has("CL Holdings drops from first to second and Encore Capital from fourth to seventh")
