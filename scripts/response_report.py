"""Part 3: write results/HOW_COMPANIES_RESPOND.md, its CSVs and charts 09-12 from the committed data.

    python scripts/response_report.py
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from complaints import response as R, taxonomy as T  # noqa: E402
from scripts.profile_report import (BLUE, GRID, INK, INK_2, MUTED, ORANGE, SAVE, SURFACE,  # noqa: E402
                                    _style, md_table, n, pct)
from scripts.sources_report import mon, of, short  # noqa: E402

RESULTS = ROOT / "results"
REPORT = "HOW_COMPANIES_RESPOND.md"
DARK_BLUE, LIGHT_BLUE = "#184f95", "#6da7ec"   # two steps of the reference blue ramp: monetary / non-monetary
EXAMPLE_ISSUE = (T.DEBT_COLLECTION, "Attempts to collect debt not owed")


def pp(x: float, nd: int = 1) -> str:
    """Percentage points, signed."""
    return f"{100 * x:+.{nd}f} pts".replace("-", "−")


def ratio_words(k: float) -> str:
    return f"{k:,.0f}"


def _xaxis_pct(ax, axis: str = "x") -> None:
    f = mticker.FuncFormatter(lambda v, _p: f"{v:.0f}%")
    (ax.xaxis if axis == "x" else ax.yaxis).set_major_formatter(f)


def _clean(ax, grid: str = "x") -> None:
    for side in ("top", "right", "left") if grid == "x" else ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis=grid, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


# ---------------------------------------------------------------- charts

def chart_outcomes(bp: pd.DataFrame, path: Path) -> None:
    d = bp.sort_values("final_responses").reset_index(drop=True)
    labels = [short(p) for p in d["product"]]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 5), sharey=True, gridspec_kw={"width_ratios": [1.25, 1]})
    a1.barh(labels, 100 * d["monetary_rate"], color=DARK_BLUE, height=0.62, label="Monetary relief",
            edgecolor=SURFACE, linewidth=1)
    a1.barh(labels, 100 * d["non_monetary_rate"], left=100 * d["monetary_rate"], color=LIGHT_BLUE, height=0.62,
            label="Non-monetary relief", edgecolor=SURFACE, linewidth=1)
    for y, (m, r) in enumerate(zip(d["monetary_rate"], d["relief_rate"])):
        a1.text(100 * r + 0.8, y, f"{pct(r)}  ({pct(m)} money)", va="center", fontsize=8.5, color=INK)
    a1.set_xlim(0, 52)
    _xaxis_pct(a1)
    _clean(a1)
    a1.tick_params(axis="y", labelcolor=INK)
    a1.set_title("Closed with relief", loc="left", fontsize=10, color=INK)
    a1.legend(frameon=False, loc="lower right", fontsize=8.5)
    a2.barh(labels, 100 * d["late_rate"], color=ORANGE, height=0.62)
    for y, r in enumerate(d["late_rate"]):
        a2.text(100 * r + 0.8, y, pct(r), va="center", fontsize=8.5, color=INK)
    a2.set_xlim(0, 42)
    _xaxis_pct(a2)
    _clean(a2)
    a2.set_title("Late (not timely, either form)", loc="left", fontsize=10, color=INK)
    fig.suptitle("How complaints end, by product, FY2026", x=0.012, ha="left", fontsize=12, fontweight="bold",
                 color=INK)
    fig.text(0.012, 0.9, "Share of final responses (complaints still in progress left out). Products ordered by "
             "complaints, largest at the top.", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_funnel(ce: pd.DataFrame, labels: list[str], path: Path) -> None:
    p = float(ce["overall_rate"].iloc[0])
    fig, ax = plt.subplots(figsize=(11, 6))
    xs = np.logspace(np.log10(ce["final_responses"].min() * 0.9), np.log10(ce["final_responses"].max() * 1.1), 200)
    sd = np.sqrt(p * (1 - p) / xs)
    for z, style in ((R.Z95, ":"), (R.Z998, "--")):
        ax.plot(xs, 100 * z * sd, style, color=MUTED, linewidth=1.2)
        ax.plot(xs, -100 * z * sd, style, color=MUTED, linewidth=1.2)
    inside = ce[ce["verdict"] == "within"]
    out = ce[ce["verdict"] != "within"]
    ax.scatter(out["final_responses"], 100 * out["difference"], s=22, color=ORANGE, edgecolor=SURFACE,
               linewidth=0.8, zorder=3, label=f"Outside the 99.8% chance limits ({len(out)})")
    ax.scatter(inside["final_responses"], 100 * inside["difference"], s=22, color=BLUE, edgecolor=SURFACE,
               linewidth=0.8, zorder=4, label=f"Inside them ({len(inside)})")
    ax.axhline(0, color=INK_2, linewidth=1)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:,.0f}"))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:+.0f}".replace("-", "−").replace("+0", "0")))
    for c in labels:
        r = ce.loc[ce["company"] == c].iloc[0]
        y = 100 * r["difference"]
        ax.annotate(c, (r["final_responses"], y), xytext=(-8, 0),
                    textcoords="offset points", ha="right", va="center", fontsize=8, color=INK)
    _clean(ax, "y")
    ax.set_xlabel("Final responses in FY2026 (log scale)")
    ax.set_ylabel("Relief rate minus peers with the same mix (points)")
    ax.plot([], [], "--", color=MUTED, linewidth=1.2, label="99.8% chance limits")
    ax.plot([], [], ":", color=MUTED, linewidth=1.2, label="95% chance limits")
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=4, fontsize=8.5)
    fig.suptitle(f"{len(out)} of {len(ce)} companies are further from their peers than chance allows",
                 x=0.012, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.905, f"Companies with {R.MIN_RESPONSES}+ final responses. Peers = every other company, "
             "same product and issue. Limits drawn\nat the all-company rate; chance alone would put about one company outside the dashed lines.",
             fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_by_month(m_all: pd.DataFrame, m_ex: pd.DataFrame, who: str, path: Path) -> None:
    d = pd.to_datetime(m_all["month"] + "-01")
    fig, ax = plt.subplots(figsize=(10.5, 5))
    ax.plot(d, 100 * m_all["relief_rate"], color=BLUE, linewidth=2, marker="o", markersize=5, label="All companies")
    ax.plot(d, 100 * m_all["expected_rate"], color=MUTED, linewidth=2, linestyle="--",
            label="Expected from the month's product and issue mix")
    ax.plot(d, 100 * m_ex["relief_rate"], color=ORANGE, linewidth=2, marker="o", markersize=5,
            label=f"Without {who}")
    last = d.iloc[-1].to_pydatetime()
    ends = [(m_all["relief_rate"].iloc[-1], "All companies"), (m_ex["relief_rate"].iloc[-1], f"Without {who}"),
            (m_all["expected_rate"].iloc[-1], "Expected from mix")]
    ends.sort(key=lambda t: -t[0])
    ys, prev = [], None
    for v, _lab in ends:                      # keep end labels at least 0.45 points apart
        y = 100 * v if prev is None else min(100 * v, prev - 0.45)
        ys.append(y)
        prev = y
    for (v, lab), y in zip(ends, ys):
        ax.text(last + timedelta(days=8), y, lab, va="center", fontsize=8.5, color=INK)
    ax.set_xlim(d.iloc[0].to_pydatetime() - timedelta(days=12), last + timedelta(days=80))
    ax.set_xticks(list(d.iloc[::2]))
    ax.set_ylim(14, 25)
    _xaxis_pct(ax, "y")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b\n%Y"))
    _clean(ax, "y")
    ax.set_ylabel("Final responses closed with relief")
    ax.legend(frameon=False, loc="upper left", fontsize=8.5)
    fig.suptitle("The rise in relief from May 2026 is one company", x=0.012, ha="left", fontsize=12,
                 fontweight="bold", color=INK)
    fig.text(0.012, 0.9, f"FY2026 by month received. {who} closed under 8% of complaints with relief each month "
             "to April, and around 90% from May.", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_late(lt: pd.DataFrame, path: Path, k: int = 12) -> None:
    d = lt.head(k).iloc[::-1]
    fig, ax = plt.subplots(figsize=(11, 5.4))
    ax.barh(list(d["company"]), d["late"], color=ORANGE, height=0.62)
    for y, (l, f, r) in enumerate(zip(d["late"], d["final_responses"], d["late_rate"])):
        ax.text(l + 60, y, f"{n(l)}  ({pct(r, 0)} of its {n(f)})", va="center", fontsize=8.5, color=INK)
    ax.set_xlim(0, d["late"].max() * 1.45)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:,.0f}"))
    _clean(ax)
    ax.tick_params(axis="y", labelcolor=INK)
    ax.set_xlabel("Late responses, FY2026 (both forms)")
    top2 = lt["late"].head(2).sum() / lt["late"].sum()
    fig.suptitle(f"Two student-loan names make up {pct(top2, 0)} of late responses", x=0.012, ha="left",
                 fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.9, f"The {k} companies with the most late responses. In brackets: the share of the company's "
             "final responses that were late.", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    fig.savefig(path, **SAVE)
    plt.close(fig)


# ---------------------------------------------------------------- report

def name(c: str) -> str:
    """Company names are shown as filed."""
    return c


def build_report(out: Path = RESULTS) -> str:
    charts = out / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    con = R.connect()
    bp = R.by_product(con)
    tot = R.totals(con)
    ce = R.company_expected(con)
    cs = R.chance_summary(ce)
    cm = R.company_expected(con, "monetary")
    ms = R.chance_summary(cm)
    me = R.mix_effect(ce)
    spr = R.spread_by_product(con)
    ex = R.issue_spread(con, *EXAMPLE_ISSUE)
    h = R.halves(con)
    sh = R.shifts(h)
    r1, r2 = R.half_rates(h)
    lead = h.iloc[0]                              # largest contribution to the change in relief
    m_all = R.by_month(con)
    m_ex = R.by_month(con, (lead["company"],))
    lead_m = R.company_months(con, lead["company"])
    h_ex = h[h["company"] != lead["company"]]
    r1x, r2x = float(h_ex["relief1"].sum() / h_ex["n1"].sum()), float(h_ex["relief2"].sum() / h_ex["n2"].sum())
    lt = R.late_by_company(con)
    ls = R.late_summary(lt)
    rc = R.repeats_check(con)

    biggest = ce.head(10)["company"].tolist()
    label_set = list(dict.fromkeys([lead["company"], "Block, Inc.", "Paypal Holdings, Inc",
                                    "Portfolio Recovery Associates, LLC", "CAPITAL ONE FINANCIAL CORPORATION",
                                    "Kriya Capital, LLC", "I.C. System, Inc."]))
    label_set = [c for c in label_set if c in set(ce["company"])]
    chart_outcomes(bp, charts / "09_outcomes_by_product.png")
    chart_funnel(ce, label_set, charts / "10_relief_against_peers.png")
    chart_by_month(m_all, m_ex, lead["company"], charts / "11_relief_by_month.png")
    chart_late(lt, charts / "12_late_responses_by_company.png")

    csv = {"index": False, "lineterminator": "\n", "float_format": "%.6f"}
    bp.to_csv(out / "outcomes_by_product.csv", **csv)
    ce.to_csv(out / "relief_against_peers.csv", **csv)
    cm.to_csv(out / "monetary_relief_against_peers.csv", **csv)
    spr.to_csv(out / "relief_spread_by_product.csv", **csv)
    h.to_csv(out / "relief_by_half.csv", **csv)
    m_all.assign(rate_without_lead=m_ex["relief_rate"].values, expected_without_lead=m_ex["expected_rate"].values) \
        .to_csv(out / "relief_by_month.csv", **csv)
    lt.to_csv(out / "late_by_company.csv", **csv)

    b = bp.set_index("product")
    dc, sl = b.loc[T.DEBT_COLLECTION], b.loc[T.STUDENT]
    sdc = spr.set_index("product").loc[T.DEBT_COLLECTION]
    ex_never, ex_always = int((ex["rate"] < R.LOW).sum()), int((ex["rate"] > R.HIGH).sum())
    pre = lead_m[lead_m["month"] < "2026-05"]
    post = lead_m[lead_m["month"] >= "2026-05"]
    mo = lt.set_index("company").loc["MOHELA"]
    fsa_name = "Servicer under contract with Federal Student Aid"
    fsa = lt.set_index("company").loc[fsa_name]
    sl_late_ex = con.execute(f"""
        SELECT sum(late) / count(*) FROM responses
        WHERE product = '{T.STUDENT}' AND company_merged NOT IN ('MOHELA', '{fsa_name}')""").fetchone()[0]
    fsa_products = con.execute(f"""
        SELECT product, count(*) AS n FROM responses WHERE company_merged = '{fsa_name}'
        GROUP BY 1 ORDER BY n DESC""").df()
    in_prog_sep = int(con.execute("""SELECT count(*) FROM complaints
        WHERE company_response = 'In progress' AND date_received >= DATE '2026-09-01'""").fetchone()[0])
    mean_shift = me["mean_abs_raw"] - me["mean_abs_adjusted"]
    top10 = ce.head(10)
    t10_out = int((top10["verdict"] != "within").sum())
    cap = ce.set_index("company")
    sdc_never, sdc_always, sdc_cos = int(sdc["almost_never"]), int(sdc["almost_always"]), int(sdc["companies"])
    shift_dir = ("all of them upwards" if (sh["shift"] > 0).all() else
                 "all of them downwards" if (sh["shift"] < 0).all() else
                 f"{int((sh['shift'] > 0).sum())} up and {int((sh['shift'] < 0).sum())} down")
    fl = me["flips"]
    fp = fl["main_product"].map(short).value_counts().sort_index().sort_values(ascending=False, kind="stable")
    flip_words = ", ".join(f"{p.lower()} ({k})" for p, k in fp.items())
    # recommendation 2 names these products; fail loudly if the data no longer says so
    if not set(fl["main_product"]) <= {T.MORTGAGE, T.STUDENT, T.PAYDAY}:
        raise ValueError(f"mix flips are no longer only mortgage/student/personal loans: {sorted(set(fl['main_product']))}")
    lead_mix = con.execute(f"""
        SELECT avg(CAST(product = '{T.DEBT_COLLECTION}' AS DOUBLE)), sum(monetary) FROM responses
        WHERE company_merged = '{lead['company'].replace("'", "''")}'""").fetchone()
    lead_dc_share, lead_money = float(lead_mix[0]), int(lead_mix[1])
    zero_months = lead_m[lead_m["relief"] == 0]["month"]
    post_min, post_max = post["relief_rate"].min(), post["relief_rate"].max()
    fsa_subs = con.execute(f"""
        SELECT product, sub_product, count(*) AS n FROM responses WHERE company_merged = '{fsa_name}'
        GROUP BY ALL ORDER BY n DESC LIMIT 2""").df()
    money_share = {p: b.loc[p, "monetary_rate"] / b.loc[p, "relief_rate"] for p in (T.CREDIT_CARD, T.CHECKING)}
    out_z = ce.loc[ce["verdict"] != "within", "z"].abs()
    n_late_rows = 15

    L: list[str] = []
    add = L.append
    add("# Part 3: how companies respond\n")
    add("Generated by `scripts/response_report.py` from the committed data. Do not edit by hand.\n")
    add("## Short answer\n")
    add(f"- **One complaint in five ends with relief, and what counts as relief depends on the product.** Of "
        f"{n(tot['final_responses'])} final responses, {pct(tot['relief_rate'])} were closed with relief, "
        f"{pct(tot['monetary_rate'])} with money. Credit cards ({pct(b.loc[T.CREDIT_CARD, 'relief_rate'])}) and "
        f"debt collection ({pct(dc['relief_rate'])}) are highest, but in debt collection almost all of it is "
        f"non-monetary ({pct(dc['monetary_rate'])} money).")
    add(f"- **Companies differ far more than chance allows, even against peers with the same products and "
        f"issues.** {cs['outside_998']} of the {cs['companies']} companies with {R.MIN_RESPONSES}+ final responses "
        f"are outside the 99.8% chance limits on relief (chance alone would put about {cs['chance_998']:.0f} "
        f"there): {cs['below']} below their peers and {cs['above']} above. Allowing for mix barely narrows the gap: "
        f"the average distance from the benchmark goes from {100 * me['mean_abs_raw']:.1f} to "
        f"{100 * me['mean_abs_adjusted']:.1f} points.")
    add(f"- **In debt collection, relief looks like a recording habit as much as an outcome.** {sdc_never} "
        f"of {sdc_cos} collectors with {R.MIN_RESPONSES}+ final responses closed under {pct(R.LOW, 0)} of "
        f"complaints with relief and {sdc_always} closed over {pct(R.HIGH, 0)}. On the same issue "
        f"(\"{EXAMPLE_ISSUE[1].lower()}\") {ex_never} of {len(ex)} collectors are under {pct(R.LOW, 0)} and "
        f"{ex_always} are over {pct(R.HIGH, 0)}.")
    add(f"- **The rise in relief during the year is one company changing how it closes complaints.** The relief "
        f"rate went from {pct(r1)} (October to March) to {pct(r2)} (April to September). {lead['company']} "
        f"closed {pct(pre['relief'].sum() / pre['final_responses'].sum())} of its complaints with relief up to "
        f"April and {pct(post['relief'].sum() / post['final_responses'].sum())} from May; without it the rate "
        f"goes from {pct(r1x)} to {pct(r2x)}. {len(sh)} companies with {R.HALF_MIN}+ responses in each half "
        f"moved by {100 * R.SHIFT_MIN:.0f} points or more, {shift_dir}.")
    add(f"- **Late responses are a few companies' problem.** {pct(tot['late_rate'])} of final responses were late "
        f"({n(tot['late'])}). {ls['companies_for_half']} companies make up half of them, and two names linked to "
        f"student loans make up {pct(ls['top2_share'], 0)}: MOHELA ({pct(mo['late_rate'], 0)} of its "
        f"{n(mo['final_responses'])} final responses late) and the entry \"{fsa_name}\" ({pct(fsa['late_rate'], 0)} "
        f"of {n(fsa['final_responses'])}). {ls['large_zero']} of the {ls['large']} large companies were never late.")
    add(f"- **The repeats change nothing.** Without the identical repeat complaints, {rc['same_verdict']} of "
        f"{rc['both']} companies keep the same verdict against their peers.\n")

    add("## 1. How complaints end, by product\n")
    add("![How complaints end, by product](charts/09_outcomes_by_product.png)\n")
    add(f"Outcomes are read on **final responses** only: {n(bp['in_progress'].sum())} complaints were still in "
        f"progress at the snapshot ({n(in_prog_sep)} of them received in September 2026) and are left out. "
        "An \"Untimely response\" is final: the company did not respond in time, so it counts as no relief. "
        "**Late** counts both forms of not timely from Part 1: the untimely responses and responses that were "
        "closed but flagged as not timely (`sql/responses.sql`).\n")
    add(md_table(pd.DataFrame({
        "Product": bp["product"].map(short), "Final responses": bp["final_responses"].map(n),
        "Relief": bp["relief_rate"].map(pct), "of which money": bp["monetary_rate"].map(pct),
        "Explanation only": bp["explanation_rate"].map(pct), "Late": bp["late_rate"].map(pct),
        "Untimely response": bp["untimely_response"].map(n), "Closed late": bp["closed_late"].map(n),
        "Companies": bp["companies"].map(n),
    })))
    add(f"\n**All products:** {n(tot['final_responses'])} final responses, relief {pct(tot['relief_rate'])}, "
        f"money {pct(tot['monetary_rate'])}, late {pct(tot['late_rate'])} ({n(tot['untimely_response'])} untimely "
        f"responses + {n(tot['closed_late'])} closed late). Relief is not the same thing in every product: "
        f"for credit cards {pct(money_share[T.CREDIT_CARD], 0)} of relief is monetary and for bank accounts "
        f"{pct(money_share[T.CHECKING], 0)}, while in debt collection almost none is "
        f"({n(dc['monetary_relief'])} of {n(dc['monetary_relief'] + dc['non_monetary_relief'])}), so the product "
        "rates are not one scale. Student loans have the lowest relief "
        f"({pct(sl['relief_rate'])}) and by far the most late responses ({pct(sl['late_rate'])}; section 4).\n")

    add("## 2. Companies against their peers\n")
    add("**Method** (`sql/company_expected.sql`). A company's raw relief rate says as much about what it is "
        "complained about as about how it responds, so each company is compared with an **expected** rate: for "
        "every one of its complaints, the relief rate of all *other* companies on the same product and issue "
        f"(if those peers have fewer than {R.MIN_PEER} final responses on it, the product's rate without the "
        "company is used). Leaving the company out matters: several companies are a large share of their "
        "own cells. The chance limits are the usual funnel-plot ones: how far from the expected count a company "
        "would land by chance alone if it handled complaints like its peers (binomial variance). Only the "
        f"{cs['companies']} companies with {R.MIN_RESPONSES}+ final responses are compared; they have "
        f"{n(cs['responses'])} of the {n(tot['final_responses'])} final responses.\n")
    add("![Relief against peers](charts/10_relief_against_peers.png)\n")
    add(f"- **Chance explains almost none of the spread.** {cs['outside_998']} of {cs['companies']} companies "
        f"are outside the 99.8% limits ({cs['outside_95']} outside the 95% limits), against about "
        f"{cs['chance_998']:.1f} and {cs['chance_95']:.0f} by chance. On **monetary** relief "
        f"(`results/monetary_relief_against_peers.csv`) {ms['outside_998']} are outside the 99.8% limits, "
        f"{ms['below']} below and {ms['above']} above.")
    add(f"- **Most companies sit below their peers, a few far above.** {cs['below']} are below the limits and "
        f"{cs['above']} above. Peer rates pool all other companies' responses, so large companies with high "
        "relief rates weigh heavily in them, and the typical company falls below.")
    add(f"- **Mix changes little.** The average distance from the benchmark is {100 * me['mean_abs_raw']:.1f} "
        f"points on raw rates and {100 * me['mean_abs_adjusted']:.1f} after allowing for product and issue "
        f"({100 * mean_shift:.1f} points less). It changes the direction for {len(fl)} companies: "
        f"{100 * me['threshold']:.0f}+ points below the all-company rate on raw figures, but above peers with the "
        f"same mix. By main product: {flip_words}. Relief is rare for everyone in these products:")
    add("")
    add(md_table(pd.DataFrame({
        "Company": fl["company"].map(name), "Main product": fl["main_product"].map(short),
        "Final responses": fl["final_responses"].map(n), "Relief": fl["rate"].map(pct),
        "All companies": fl["overall_rate"].map(pct), "Peers, same mix": fl["expected_rate"].map(pct),
        "Against chance limits": fl["verdict"],
    }), "llrrrrl"))
    add(f"\n**The 10 companies with the most final responses** ({t10_out} of 10 outside the 99.8% limits):\n")
    add(md_table(pd.DataFrame({
        "Company": top10["company"].map(name), "Main product": top10["main_product"].map(short),
        "Final responses": top10["final_responses"].map(n), "Relief": top10["rate"].map(pct),
        "Peers, same mix": top10["expected_rate"].map(pct), "Difference": top10["difference"].map(pp),
        "Against chance limits": top10["verdict"],
    }), "llrrrrl"))
    add(f"\nEvery company is in `results/relief_against_peers.csv` (observed, expected, z-score and verdict). "
        f"For example, Capital One closed {pct(cap.loc['CAPITAL ONE FINANCIAL CORPORATION', 'rate'])} of complaints "
        f"with relief against {pct(cap.loc['CAPITAL ONE FINANCIAL CORPORATION', 'expected_rate'])} for peers with "
        f"its mix, and Citibank {pct(cap.loc['CITIBANK, N.A.', 'rate'])} against "
        f"{pct(cap.loc['CITIBANK, N.A.', 'expected_rate'])}.\n")

    add("### Why the spread is so wide: relief is recorded differently\n")
    add(f"Within one product, many companies almost never record relief and a few almost always do "
        f"(companies with {R.MIN_RESPONSES}+ final responses in the product; `results/relief_spread_by_product.csv`):\n")
    add(md_table(pd.DataFrame({
        "Product": spr["product"].map(short), "Companies": spr["companies"],
        f"Under {pct(R.LOW, 0)} relief": spr["almost_never"], f"Over {pct(R.HIGH, 0)}": spr["almost_always"],
        "Median company": spr["median_company"].map(pct),
        "Middle half of companies": [f"{pct(a)} to {pct(b)}" for a, b in zip(spr["p25"], spr["p75"])],
        "All their responses": spr["pooled"].map(pct),
    })))
    add(f"\nThe clearest case is debt collection on a single issue, \"{EXAMPLE_ISSUE[1]}\": of the {len(ex)} "
        f"collectors with {R.MIN_RESPONSES}+ final responses on it, {ex_never} closed under {pct(R.LOW, 0)} with "
        f"relief and {ex_always} over {pct(R.HIGH, 0)}, for the same complaint chosen from the same list. "
        "The data cannot say whether these companies treat consumers that differently or record the same kind "
        "of answer under different labels (for example, whether stopping collection on a disputed debt is "
        "logged as relief or as an explanation). Either way, **a company's relief rate is only comparable with "
        "its own history** unless the labelling rules are known, which is why section 3 looks for changes "
        "within a company.\n")

    add("## 3. Changes during the year\n")
    add("![Relief by month](charts/11_relief_by_month.png)\n")
    add(f"The relief rate rose from {pct(r1)} in the first half of FY2026 (October to March) to {pct(r2)} in the "
        f"second (April to September), while the rate expected from each month's product and issue mix stayed "
        f"between {pct(m_all['expected_rate'].min())} and {pct(m_all['expected_rate'].max())}. So the rise is "
        "not a change in what people complained about. Splitting the change by company "
        f"(`sql/relief_halves.sql`; the contributions add up exactly to the change), **{lead['company']}** makes up "
        f"{pp(lead['contribution'])} of the {pp(r2 - r1)}: more than all of it.\n")
    add(md_table(pd.DataFrame({
        "Month received": lead_m["month"].map(mon), "Final responses": lead_m["final_responses"].map(n),
        "Closed with relief": lead_m["relief"].map(n), "Relief rate": lead_m["relief_rate"].map(pct),
    })))
    add(f"\n{pct(lead_dc_share, 0)} of {lead['company']}'s complaints are about debt collection. It closed every "
        f"complaint received from {mon(zero_months.min())} to {mon(zero_months.max())} without relief, then "
        f"between {pct(post_min, 0)} and {pct(post_max, 0)} with relief in every month from May 2026, all of it "
        f"non-monetary ({'none' if lead_money == 0 else n(lead_money)} with money all year). Without it, the all-company rate goes from {pct(r1x)} "
        f"to {pct(r2x)}. The data does not say what changed: a new way of handling these complaints, or a new "
        "way of recording the same answers.\n")
    add(f"**Companies that changed** ({R.HALF_MIN}+ final responses in each half, relief rate moved by "
        f"{100 * R.SHIFT_MIN:.0f} points or more, beyond the 99.8% chance limit; `results/relief_by_half.csv`):\n")
    add(md_table(pd.DataFrame({
        "Company": sh["company"].map(name), "Oct-Mar responses": sh["n1"].map(n), "Oct-Mar relief": sh["rate1"].map(pct),
        "Apr-Sep responses": sh["n2"].map(n), "Apr-Sep relief": sh["rate2"].map(pct), "Change": sh["shift"].map(pp),
    })))
    add("\nFor a compliance team this is the use of the data that holds up: **a step change in a company's own "
        "outcome mix** is either a real change in how complaints are handled or a change in how they are "
        "recorded, and both are worth knowing about. Part 4 turns this into a monitor.\n")

    add("## 4. Timeliness\n")
    add("![Late responses by company](charts/12_late_responses_by_company.png)\n")
    add(f"Timeliness is the CFPB's own yes/no flag (\"Timely response?\"), recorded the same way for every "
        f"product and company, so lateness is compared directly, with no allowance for mix "
        f"(`sql/late_by_company.sql`). {n(ls['late'])} final "
        f"responses were late ({pct(tot['late_rate'])}), at {n(ls['companies_with_late'])} of "
        f"{n(ls['companies'])} companies.\n")
    add(f"- **It is concentrated.** {ls['companies_for_half']} companies make up half of all late responses and "
        f"{ls['companies_for_80']} make up 80%. MOHELA alone is {pct(mo['late'] / ls['late'], 0)}: "
        f"{n(mo['late'])} of its {n(mo['final_responses'])} final responses were late ({n(mo['untimely_response'])} "
        f"untimely responses, {n(mo['closed_late'])} closed late).")
    add(f"- **\"{fsa_name}\" was late on all {n(fsa['final_responses'])} of its final responses**, every one an "
        f"untimely response. The entry names no company. Most of its complaints are "
        + " and ".join(f"{short(p).lower()} with sub-product \"{sp_}\" ({n(k)})"
                       for p, sp_, k in zip(fsa_subs["product"], fsa_subs["sub_product"], fsa_subs["n"]))
        + f", out of {n(fsa_products['n'].sum())}.")
    add(f"- **Student loans are late because of those two.** Without them, {pct(sl_late_ex)} of student-loan "
        f"final responses were late, against {pct(sl['late_rate'])} with them.")
    add(f"- **Most large companies are rarely late.** Of the {ls['large']} companies with {R.MIN_RESPONSES}+ final "
        f"responses, {ls['large_zero']} were never late and {ls['large_10pct']} were late on 10% or more.\n")
    big_late = lt[(lt["final_responses"] >= R.MIN_RESPONSES) & (lt["late_rate"] >= 0.10)]
    add(f"The {min(n_late_rows, len(big_late))} of these {len(big_late)} with the most late responses (all of them "
        "are in `results/late_by_company.csv`):\n")
    big_late = big_late.head(n_late_rows)
    add(md_table(pd.DataFrame({
        "Company": big_late["company"].map(name), "Main product": big_late["main_product"].map(short),
        "Final responses": big_late["final_responses"].map(n), "Late": big_late["late"].map(n),
        "Late rate": big_late["late_rate"].map(lambda x: pct(x, 0)),
        "of which untimely response": big_late["untimely_response"].map(n),
    }), "llrrrr"))
    add("")

    add("## 5. Do the repeats change anything?\n")
    ch = rc["changed"]
    add(f"Part 1 found 17,349 complaints identical to an earlier one on every field except the ID. Rerunning the "
        f"peer comparison without them (`where = NOT is_repeat`): {rc['same_verdict']} of {rc['both']} companies "
        f"keep the same verdict"
        + (f" ({', '.join(f'{name(c)}: {a} → {b}' for c, a, b in zip(ch['company'], ch['verdict'], ch['verdict_nr']))})"
           if len(ch) else "")
        + f", the differences from peers correlate at {rc['correlation']:.4f}, and no company's difference moves "
        f"by more than {100 * rc['max_shift']:.1f} points.\n")

    add("## So what for a complaints or compliance team\n")
    add("1. **Don't benchmark your relief rate against other companies' published rates** without knowing how "
        "they record relief: on the same product and issue, collectors range from almost never to almost always. "
        "Benchmark against your own history, and against peers only on outcomes with a shared definition "
        "(timeliness, which the CFPB flags the same way for everyone).")
    add(f"2. **Allow for mix anyway, then look at the size of the gap.** It moves the average gap by only "
        f"{100 * mean_shift:.1f} points, but for mortgage, student-loan and personal-loan companies, where relief is rare, it can turn \"below average\" into "
        "\"above peers\".")
    add(f"3. **Watch for step changes in your own outcome mix.** One collector's change moved the relief rate "
        f"across all companies by {pp(lead['contribution'])} between the two halves of the year; a change like "
        "that in your own data needs an explanation before it reaches a board report.")
    add("4. **Timeliness is the clean comparison.** The CFPB flags it the same way for everyone, most large "
        "companies are rarely late, and the misses sit with a handful of firms, led by student-loan servicing.\n")

    add("## Limits\n")
    add("- Relief and explanation are the company's own description of its response; the CFPB does not verify "
        "them, and consumers' feedback on responses is not published.")
    add("- Expected rates use product and issue only; sub-product, state or how the complaint was submitted could "
        "also differ between companies. The fallback to product level covers few responses "
        f"({n(ce['fallback_responses'].fillna(0).sum())} of {n(cs['responses'])}).")
    add(f"- The chance limits assume complaints are independent; repeats and campaigns make them less so, which "
        f"would widen the limits. The median company outside the 99.8% limits is {out_z.median():.1f} standard "
        f"deviations from its expected count, against {R.Z998:.1f} at the limit.")
    add("- Outcomes for the last months are those already final at the snapshot; responses still in progress "
        "(most from September 2026) may end differently.")
    return "\n".join(L) + "\n"


def write(out: Path = RESULTS) -> str:
    out.mkdir(parents=True, exist_ok=True)
    report = build_report(out)
    (out / REPORT).write_text(report)
    return report


def main() -> int:
    report = write()
    print(f"wrote results/{REPORT} ({len(report.splitlines())} lines), 7 CSVs and 4 charts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
