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
    assert "**Status: in progress. Parts 1 to 3 of 5 are done" in README
    charts = re.findall(r"\(results/charts/([^)]+\.png)\)", README)
    assert charts == ["01_history_by_month.png", "02_fy2026_by_product.png",
                      "05_products_by_month.png", "07_growth_with_and_without_spikes.png",
                      "10_relief_against_peers.png", "11_relief_by_month.png"]
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


# ---------------------------------------------------------------- Part 3

@pytest.fixture(scope="module")
def part3():
    from complaints import response as R, taxonomy as T
    con = R.connect()
    bp = R.by_product(con).set_index("product")
    tot = R.totals(con)
    ce = R.company_expected(con)
    h = R.halves(con)
    lead = h.iloc[0]
    hx = h[h["company"] != lead["company"]]
    lm = R.company_months(con, lead["company"])
    m = R.by_month(con)
    lt = R.late_by_company(con)
    spr = R.spread_by_product(con).set_index("product")
    ex = R.issue_spread(con, T.DEBT_COLLECTION, "Attempts to collect debt not owed")
    lead_dc = con.execute(f"""SELECT avg(CAST(product = '{T.DEBT_COLLECTION}' AS DOUBLE)) FROM responses
                             WHERE company_merged = '{lead["company"]}'""").fetchone()[0]
    fsa = "Servicer under contract with Federal Student Aid"
    sl_ex = con.execute(f"""SELECT avg(late) FROM responses WHERE product = '{T.STUDENT}'
                           AND company_merged NOT IN ('MOHELA', '{fsa}')""").fetchone()[0]
    return dict(R=R, T=T, con=con, bp=bp, tot=tot, ce=ce, cs=R.chance_summary(ce), me=R.mix_effect(ce), h=h,
                lead=lead, hx=hx, lm=lm, m=m, lt=lt, ls=R.late_summary(lt), spr=spr, ex=ex, lead_dc=lead_dc,
                fsa=fsa, sl_ex=sl_ex, rc=R.repeats_check(con))


def test_part3_outcomes(part3):
    t, bp, T = part3["tot"], part3["bp"], part3["T"]
    dc, cc = bp.loc[T.DEBT_COLLECTION], bp.loc[T.CREDIT_CARD]
    has(f"{n(t['final_responses'])} final responses", f"the {n(bp['in_progress'].sum())} still in progress",
        f"**One complaint in five ends with relief**: {pct(t['relief_rate'])}, and {pct(t['monetary_rate'])} with money",
        f"for credit cards {pct(cc['monetary_rate'] / cc['relief_rate'], 0)} of it is monetary",
        f"({n(dc['monetary_relief'])} of {n(dc['monetary_relief'] + dc['non_monetary_relief'])})")
    assert 0.18 <= t["relief_rate"] <= 0.22          # "one in five"


def test_part3_peers(part3):
    cs, me, spr, ex, T, R = part3["cs"], part3["me"], part3["spr"], part3["ex"], part3["T"], part3["R"]
    has(f"The {cs['companies']} companies with 100 or more final responses",
        f"{cs['outside_998']} of the {cs['companies']} are outside the 99.8% limits, where chance alone would put "
        f"about one: {cs['below']} below their peers and {cs['above']} above",
        f"goes from {100 * me['mean_abs_raw']:.1f} to {100 * me['mean_abs_adjusted']:.1f} points")
    assert round(cs["chance_998"]) == 1
    fl = me["flips"]
    assert len(fl) == 6 and "turns six mortgage, student-loan and personal-loan companies" in README
    assert set(fl["main_product"]) == {T.MORTGAGE, T.STUDENT, T.PAYDAY}
    assert (fl["raw_difference"] <= -0.05).all() and (fl["difference"] > 0).all()
    d = spr.loc[T.DEBT_COLLECTION]
    has(f"{int(d['almost_never'])} of {int(d['companies'])} collectors closed under 2% of complaints with relief and "
        f"{int(d['almost_always'])} over 90%",
        f"{int((ex['rate'] < R.LOW).sum())} of {len(ex)} collectors are under 2% and "
        f"{int((ex['rate'] > R.HIGH).sum())} over 90%")
    rc = part3["rc"]
    has(f"{rc['same_verdict']} of {rc['both']} companies keep the same verdict")


def test_part3_change_in_the_year(part3):
    h, hx, lead, lm, m, R = part3["h"], part3["hx"], part3["lead"], part3["lm"], part3["m"], part3["R"]
    r1, r2 = R.half_rates(h)
    pre, post = lm[lm["month"] < "2026-05"], lm[lm["month"] >= "2026-05"]
    has(f"Relief went from {pct(r1)} (October to March) to {pct(r2)} (April to September)",
        f"stayed between {pct(m['expected_rate'].min())} and {pct(m['expected_rate'].max())}",
        f"{lead['company']} ({pct(part3['lead_dc'], 0)} of its complaints are about debt collection) closed "
        f"{pct(pre['relief'].sum() / pre['final_responses'].sum())} of its complaints with relief up to April and "
        f"{pct(post['relief'].sum() / post['final_responses'].sum())} from May",
        f"flat ({pct(hx['relief1'].sum() / hx['n1'].sum())} to {pct(hx['relief2'].sum() / hx['n2'].sum())})",
        f"by {100 * lead['contribution']:.1f} points")
    assert lead["contribution"] > r2 - r1            # "more than all of it" in the report
    assert lead["company"] == "CL Holdings LLC"


def test_part3_late(part3):
    lt, ls, t, bp, T = part3["lt"], part3["ls"], part3["tot"], part3["bp"], part3["T"]
    mo, fsa = lt.set_index("company").loc["MOHELA"], lt.set_index("company").loc[part3["fsa"]]
    has(f"{pct(t['late_rate'])} of final responses were late",
        f"{ls['companies_for_half']} companies make up half of them",
        f"MOHELA ({pct(mo['late_rate'], 0)} of its {n(mo['final_responses'])} late)",
        f"({pct(fsa['late_rate'], 0)} of {n(fsa['final_responses'])}) make up {pct(ls['top2_share'], 0)}",
        f"{pct(part3['sl_ex'])} of student-loan responses were late, not {pct(bp.loc[T.STUDENT, 'late_rate'])}",
        f"{ls['large_zero']} of the {ls['large']} large companies were never late")
    assert list(lt["company"].head(2)) == ["MOHELA", part3["fsa"]]
