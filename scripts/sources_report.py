"""Part 2: write results/WHERE_COMPLAINTS_COME_FROM.md, its CSVs and charts 05-08 from the committed data.

    python scripts/sources_report.py
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from complaints import mix as M, taxonomy as T  # noqa: E402
from scripts.profile_report import (BLUE, GRID, INK, INK_2, MUTED, ORANGE, SAVE, SURFACE,  # noqa: E402
                                    _style, md_table, n, pct)

RESULTS = ROOT / "results"
REPORT = "WHERE_COMPLAINTS_COME_FROM.md"
CHART_FROM = "2017-10"   # charts start with FY2018, the first full year under the April 2017 product list

# Public events in the same month as a spike, about the company behind most of it (checked against the
# sources linked; timing alone does not show that the event caused the complaints).
EVENTS = {
    ("Student loan", "2017-01"): ("the CFPB sued Navient on 18 January 2017",
                                  "https://www.consumerfinance.gov/enforcement/actions/navient-corporation-navient-solutions-inc-and-pioneer-credit-recovery-inc/"),
    (T.CREDIT_REPORTING, "2017-09"): ("Equifax disclosed its data breach on or about 7 September 2017",
                                      "https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach"),
    (T.CHECKING, "2023-01"): ("on 20 December 2022 the CFPB ordered Wells Fargo to pay $3.7 billion over its handling "
                              "of auto loans, mortgages and deposit accounts",
                              "https://www.consumerfinance.gov/enforcement/actions/wells-fargo-bank-na-2022/"),
}


def short(p: str) -> str:
    return T.SHORT.get(p, p)


def signed(x: float, nd: int = 1) -> str:
    return f"{100 * x:+.{nd}f}%".replace("-", "−")


def k_label(x: float, _pos=None) -> str:
    """Axis label in thousands without rounding steps together (1.5k, not 2k)."""
    return f"{x / 1000:g}k" if x >= 1000 else f"{x:.0f}"


def of(k: int, total: int) -> str:
    """'9 of 10', or 'all 11' when every one counts."""
    return f"all {total}" if k == total else f"{k} of {total}"


def month_name(m: str) -> str:
    return pd.Timestamp(m + "-01").strftime("%B %Y")


def mon(m: str) -> str:
    return pd.Timestamp(m + "-01").strftime("%b %Y")


# ---------------------------------------------------------------- charts

def chart_small_multiples(pmo: pd.DataFrame, path: Path) -> None:
    d = pmo[pmo["month"] >= CHART_FROM].copy()
    d["date"] = pd.to_datetime(d["month"] + "-01")
    fig, axes = plt.subplots(4, 3, figsize=(12, 10.5), sharex=True)
    for ax, prod in zip(axes.flat, T.CURRENT_PRODUCTS):
        g = d[d["current_product"] == prod]
        ax.plot(g["date"], g["complaints"], color=BLUE, linewidth=1.6)
        s = g[g["status"] == "spike"]
        ax.plot(s["date"], s["complaints"], "o", color=ORANGE, markersize=7, markeredgecolor=SURFACE,
                markeredgewidth=1.5, zorder=3)
        ax.set_title(short(prod), loc="left", fontsize=10, color=INK)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(k_label))
        ax.set_ylim(0, g["complaints"].max() * 1.12)
        _style(ax)
        if len(s):
            i = s["complaints"].idxmax()
            if s.at[i, "complaints"] > g["complaints"].max() * 0.6:
                ax.text(s.at[i, "date"].to_pydatetime() - timedelta(days=40), s.at[i, "complaints"], mon(s.at[i, "month"]),
                        fontsize=8, color=INK_2, ha="right", va="top")
    for ax in axes.flat[len(T.CURRENT_PRODUCTS):]:
        ax.axis("off")
    last = axes.flat[-1]
    last.plot([0.05], [0.62], "o", color=ORANGE, markersize=7, transform=last.transAxes)
    last.text(0.11, 0.62, "Spike month: at least 1.5 times both the\nmedian of the 12 months before and of\n"
              "the 6 months after, and 250+ above it", transform=last.transAxes, va="center", fontsize=8.5,
              color=INK_2)
    last.plot([0.02, 0.08], [0.3, 0.3], color=BLUE, linewidth=1.6, transform=last.transAxes)
    last.text(0.11, 0.3, "Complaints per month, products\nmapped to current names", transform=last.transAxes,
              va="center", fontsize=8.5, color=INK_2)
    for ax in axes[-1, :]:
        ax.xaxis.set_major_locator(matplotlib.dates.YearLocator(2))
        ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y"))
    axes[2, 2].xaxis.set_tick_params(labelbottom=True)
    fig.suptitle("Complaints per month by product, October 2017 to October 2026", x=0.012, ha="left",
                 fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.943, "Each panel has its own scale. Orange dots: spike months. None falls in the FY2026 "
             "snapshot (October 2025 to September 2026).", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.935))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_spike_owners(sp: pd.DataFrame, path: Path, k: int = 12) -> None:
    d = sp.sort_values(["excess_over_average", "month"], ascending=[False, True], kind="stable").head(k).iloc[::-1]
    labels = [f"{short(p)}, {mon(m)}" for p, m in zip(d["current_product"], d["month"])]
    fig, ax = plt.subplots(figsize=(11, 5.6))
    shares = (100 * d["top_company_share"]).clip(upper=100)
    ax.barh(labels, shares, color=BLUE, height=0.62)
    for y, (s, c, x) in enumerate(zip(d["top_company_share"], d["top_company"], d["excess_over_average"])):
        ax.text(min(100, 100 * s) + 1.2, y, f"{pct(s, 0)}  {c}  (of {n(x)} extra)", va="center", fontsize=8.5,
                color=INK)
    ax.set_xlim(0, 175)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.tick_params(axis="y", labelcolor=INK)
    ax.set_xlabel("Share of the month's extra complaints from the largest single company")
    fig.suptitle(f"A spike is usually one company: the {k} largest spikes", x=0.012, ha="left",
                 fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.9, "Extra complaints = the month's count minus the average month over the 12 months "
             "before, for the product and for each company. Bars stop at 100%.", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_growth(g: pd.DataFrame, sp: pd.DataFrame, path: Path) -> None:
    d = g[g["current_product"] != T.CREDIT_REPORTING].iloc[::-1].reset_index(drop=True)
    cr = g.loc[g["current_product"] == T.CREDIT_REPORTING, "change_1y_adjusted"].iloc[0]
    sp25 = sp[sp["month"].between("2024-10", "2025-09")]
    fell = d.loc[d["change_1y_adjusted"] <= 0, "current_product"].map(short).tolist()
    title = ("Take out the spikes and every product grew" if not fell else
             f"Take out the spikes and every product grew except {' and '.join(fell)}" if len(fell) <= 2 else
             "FY2025 to FY2026, with and without the spikes")
    fig, ax = plt.subplots(figsize=(10.5, 5))
    ys = range(len(d))
    for y, a, b in zip(ys, d["change_1y"], d["change_1y_adjusted"]):
        if abs(a - b) > 1e-9:
            ax.plot([100 * a, 100 * b], [y, y], color=GRID, linewidth=2, zorder=1)
    ax.scatter(100 * d["change_1y"], ys, s=60, color=ORANGE, edgecolor=SURFACE, linewidth=1.5, zorder=3,
               label="As counted")
    ax.scatter(100 * d["change_1y_adjusted"], ys, s=60, color=BLUE, edgecolor=SURFACE, linewidth=1.5, zorder=4,
               label="Spike months at their baseline")
    for y, a, b in zip(ys, d["change_1y"], d["change_1y_adjusted"]):
        ax.text(100 * max(a, b) + 3, y, signed(b, 0) if abs(a - b) < 1e-9 else f"{signed(a, 0)} → {signed(b, 0)}",
                va="center", fontsize=8.5, color=INK)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([short(p) for p in d["current_product"]], color=INK)
    ax.set_xlim(-60, 95)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _p: f"{v:+.0f}%".replace("+0%", "0%").replace("-", "−")))
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    ax.set_xlabel("Change in complaints, FY2025 to FY2026")
    fig.suptitle(title, x=0.012, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.865, f"FY2025 had spike months in {sp25['current_product'].nunique()} products "
             f"({mon(sp25['month'].min())} to {mon(sp25['month'].max())}); FY2026 had "
             f"{'none' if not sp['month'].between('2025-10', '2026-09').any() else 'some'}.\nWhere a product had no "
             f"spike the two dots are the same and only blue shows. Credit reporting not shown ({signed(cr, 0)}).",
             fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.85))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_top_issue(top1: pd.DataFrame, path: Path) -> None:
    d = top1.sort_values("share").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.barh([short(p) for p in d["product"]], 100 * d["share"], color=BLUE, height=0.62)
    for y, (s, i) in enumerate(zip(d["share"], d["issue"])):
        ax.text(100 * s + 1, y, f"{pct(s, 0)}  {i}", va="center", fontsize=8.5, color=INK)
    ax.set_xlim(0, 125)
    ax.set_xticks([0, 20, 40, 60])
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.tick_params(axis="y", labelcolor=INK)
    ax.set_xlabel("Share of the product's FY2026 complaints")
    fig.suptitle("The most common issue in each product, FY2026", x=0.012, ha="left",
                 fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.885, "Issues as chosen by the consumer from the CFPB's list for each product.",
             fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(path, **SAVE)
    plt.close(fig)


# ---------------------------------------------------------------- report

def build_report(out: Path = RESULTS) -> str:
    charts = out / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    con = M.connect()
    pm = M.product_map(con)
    summ = M.map_summary(pm)
    pmo = M.product_months(con)
    sp = M.spikes(con)
    recent = M.recent_flags(con)
    sens = M.sensitivity(con)
    fy = M.fiscal_years(con)
    gr = M.growth(fy)
    chg = M.change_by_company(con)
    drv = M.change_drivers(chg)
    wk = M.weekly(con)
    imix = M.issue_mix(con)
    top3 = M.top_issues(imix, 3)
    top1 = M.top_issues(imix, 1)
    rob = M.robustness(con)

    chart_small_multiples(pmo, charts / "05_products_by_month.png")
    chart_spike_owners(sp, charts / "06_spike_owners.png")
    chart_growth(gr, sp, charts / "07_growth_with_and_without_spikes.png")
    chart_top_issue(top1, charts / "08_top_issue_by_product.png")

    csv = {"index": False, "lineterminator": "\n", "float_format": "%.6f"}
    pm.to_csv(out / "product_map.csv", **csv)
    pmo.to_csv(out / "product_months.csv", **csv)
    sp.to_csv(out / "spikes.csv", **csv)
    gr.to_csv(out / "growth_by_product.csv", **csv)
    drv.to_csv(out / "growth_drivers.csv", **csv)
    imix.to_csv(out / "issue_mix_fy2026.csv", **csv)
    rob["products"].to_csv(out / "repeats_check_products.csv", **csv)
    sens.to_csv(out / "spike_sensitivity.csv", **csv)

    g = gr.set_index("current_product")
    mt, ck, st = g.loc[T.MONEY], g.loc[T.CHECKING], g.loc[T.STUDENT]
    non_cr = gr[gr["current_product"] != T.CREDIT_REPORTING]
    grew_adj = non_cr[non_cr["change_1y_adjusted"] > 0]
    fell_adj = non_cr[non_cr["change_1y_adjusted"] <= 0]
    s = sp.set_index(["current_product", "month"])
    jan_mt, jan_ck = s.loc[(T.MONEY, "2025-01")], s.loc[(T.CHECKING, "2025-01")]
    one_firm = int((sp["top_company_share"] >= 0.5).sum())
    in_fy26 = int((sp["month"].between("2025-10", "2026-09")).sum())
    w_ratio = wk.assign(r=wk["complaints"] / wk[["prior_median", "next_median"]].max(axis=1))
    wmax = w_ratio.loc[w_ratio["r"].idxmax()]
    old_total = int(summ["complaints"].sum())
    total = int(pm["complaints"].sum())
    d = drv.set_index("current_product")
    dc = d.loc[T.DEBT_COLLECTION]
    wo, wi = rob["without"], rob["with"]
    t10 = rob["top10"]
    moved = t10[t10["rank"] != t10["rank_no_repeats"]]
    dc_top = top1.set_index("product").loc[T.DEBT_COLLECTION]
    two_firms = int((sp["top_company_share"] + sp["second_company_share"].fillna(0) >= 0.5).sum())
    quarter = top1[top1["share"] >= 0.25]
    rep_rate = con.execute("""
        SELECT company_merged AS company, count(*) FILTER (WHERE is_repeat) / count(*) AS repeat_share
        FROM complaints_flagged GROUP BY ALL""").df().set_index("company")["repeat_share"]
    all_rate = float(con.execute("SELECT avg(CASE WHEN is_repeat THEN 1.0 ELSE 0 END) FROM complaints_flagged").fetchone()[0])
    movers = t10.assign(shift=(t10["rank_no_repeats"] - t10["rank"])).sort_values(["shift", "rank"], ascending=[False, True])
    movers = movers[movers["shift"] > 0].head(2)

    L: list[str] = []
    add = L.append
    add("# Part 2: where complaints come from\n")
    add("Generated by `scripts/sources_report.py` from the committed data. Do not edit by hand.\n")
    add("## Short answer\n")
    add(f"- **A spike is usually one company.** The history has {len(sp)} spike months (far above both the "
        f"months before and the months after). In {one_firm} of them a single company accounts for half or more "
        f"of the extra complaints. In January 2025, Block, Inc. and Early Warning Services made up "
        f"{pct(jan_mt['top_company_share'] + jan_mt['second_company_share'], 0)} of the money-transfer spike "
        f"({n(jan_mt['complaints'])} complaints against a usual {n(jan_mt['baseline'])}), and Navy Federal Credit "
        f"Union and Capital One {pct(jan_ck['top_company_share'] + jan_ck['second_company_share'], 0)} of the "
        "bank-account spike.")
    add(f"- **Spikes distort year-on-year figures.** Counted as filed, money-transfer complaints fell "
        f"{signed(mt['change_1y'])} from FY2025 to FY2026; with the spike months set to their baseline they rose "
        f"{signed(mt['change_1y_adjusted'])}. Bank accounts go from {signed(ck['change_1y'])} to "
        f"{signed(ck['change_1y_adjusted'])}, student loans from {signed(st['change_1y'])} to "
        f"{signed(st['change_1y_adjusted'])}.")
    add(f"- **Underneath, complaints grew in {len(grew_adj)} of {len(non_cr)} products** (credit reporting aside). "
        f"Prepaid cards are flat ({signed(g.loc[T.PREPAID, 'change_1y_adjusted'])}). The largest rises: payday and "
        f"personal loans {signed(g.loc[T.PAYDAY, 'change_1y_adjusted'])}, mortgages "
        f"{signed(g.loc[T.MORTGAGE, 'change_1y_adjusted'])}, vehicle loans "
        f"{signed(g.loc[T.VEHICLE, 'change_1y_adjusted'])}. The growth is broad: in debt collection "
        f"{n(dc['companies_up'])} companies had more complaints a month and {n(dc['companies_down'])} fewer, and the "
        f"largest single contributor added {pct(dc['lead_share'], 0)} of the rise.")
    add(f"- **No spike falls inside the FY2026 snapshot**, by month ({in_fy26} of {len(sp)}) or by week (none of "
        f"{len(wk)} product-weeks), and that holds under every threshold tried. So the FY2026 product and issue "
        "mix that Parts 3 and 4 build on is not one event's footprint.")
    add(f"- **The largest issue in debt collection is debts people say they don't owe** ({pct(dc_top['share'])} "
        f"of its complaints). In {len(quarter)} of {len(top1)} products the most common issue is a quarter or more "
        "of complaints, which tells a complaints team where root-cause work pays off first.")
    add(f"- **The repeats and the two-way spellings change nothing material.** Without the {n(rob['products']['complaints'].sum() - rob['products']['complaints_no_repeats'].sum())} "
        f"repeats no product's share moves by more than {pct(rob['max_product_share_shift'], 1).replace('%', '')} "
        f"percentage points, every product keeps its top issue and the top-10 companies stay the same "
        f"10, though {len(moved)} of them change places.\n")

    add("## 1. Old product names, mapped onto current ones\n")
    add(f"The CFPB changed its product list in April 2017 and August 2023. To compare years, every complaint "
        f"is put under the product it would be filed under today (`complaints/taxonomy.py`). The history has "
        f"{len(pm)} product and sub-product pairs as filed; {n(old_total)} complaints ({pct(old_total / total, 1)} "
        f"of {n(total)}) were filed under a name that no longer exists. Four products were later split, so "
        "they are mapped by sub-product (for example, prepaid sub-products of \"Credit card or prepaid card\" go "
        "to Prepaid card). Every complaint lands on exactly one of the 11 current products, and the total is "
        "unchanged (tested).\n")
    sm = summ.copy()
    add(md_table(pd.DataFrame({
        "Current product": sm["current_product"].map(short), "Filed as": sm["product"],
        "Sub-products": sm["sub_products"], "Complaints": sm["complaints"].map(n),
        "Used": [f"{a} to {b}" for a, b in zip(sm["first_month"], sm["last_month"])],
    }), "llrrl"))
    add("\nEvery pair, with its rule, is in `results/product_map.csv`. One limit: \"Debt or credit management\" "
        "only became a product in August 2023, and two of its sub-products (mortgage modification or foreclosure "
        "avoidance, and student loan debt relief) have no earlier equivalent in the list. Earlier complaints of "
        "that kind cannot be traced, so its long-run growth is not like for like.\n")

    add("## 2. Spikes: one company, one month\n")
    add("![Complaints per month by product](charts/05_products_by_month.png)\n")
    add(f"**The rule** (`sql/product_months.sql`): a month is a spike when it is at least {M.SPIKE_RATIO} times "
        "the larger of two baselines, the median of the 12 months before and the median of the 6 months after, "
        f"and at least {M.MIN_EXCESS} complaints above it. Comparing with the months after as well as before "
        "separates a one-off from a new level: the growth of credit reporting from 2020 on is never flagged, "
        "because the months after are as high.\n")
    add("**Who is behind it** (`sql/spike_companies.sql`): each company's complaints in the spike month minus "
        "its own average month over the 12 months before. These company excesses add up exactly to the product's "
        "excess over its 12-month average.\n")
    add("![The largest spikes by company](charts/06_spike_owners.png)\n")
    tab = sp.copy()
    add(md_table(pd.DataFrame({
        "Month": tab["month"].map(mon), "Product": tab["current_product"].map(short),
        "Complaints": tab["complaints"].map(n), "Baseline": tab["baseline"].map(n),
        "Times baseline": tab["ratio"].map(lambda x: f"{x:.1f}"),
        "Largest company": tab["top_company"], "Its share of the extra": tab["top_company_share"].map(lambda x: pct(x, 0)),
    }), "llrrrlr"))
    add("\nA share above 100% means the other companies together had fewer complaints than their usual month. "
        f"In {one_firm} of the {len(sp)} spikes one company makes up half or more of the extra complaints, and in "
        f"{'all of them' if two_firms == len(sp) else two_firms} the two largest companies do. The data does not say why any spike happened. Three of them "
        "come in the same month as a public event about the company behind most of the spike, or the month "
        "after it (timing alone does not show cause):\n")
    for (prod, m), (text, url) in EVENTS.items():
        r = s.loc[(prod, m)]
        add(f"- {short(prod)}, {month_name(m)}: {r['top_company']} drew {pct(r['top_company_share'], 0)} of the "
            f"extra complaints; {text} ([source]({url})).")
    wf = sp[(sp["month"] == "2023-01") & (sp["top_company"] == "WELLS FARGO & COMPANY")]
    add(f"\nIn January 2023 Wells Fargo leads the spike in {len(wf)} products at once "
        f"({', '.join(short(p).lower() for p in wf['current_product'])}), the three areas named in the "
        "December 2022 order.\n")
    add(f"**Sensitivity** (`results/spike_sensitivity.csv`): the count of spike months depends on the "
        f"thresholds, but no setting finds one inside FY2026.\n")
    add(md_table(pd.DataFrame({
        "Times baseline": sens["ratio"], "Min. extra": sens["min_excess"], "Spike months": sens["spike_months"],
        "Products": sens["products"], "In FY2025": sens["in_fy2025"], "In FY2026": sens["in_fy2026"],
    }), "rrrrrr"))
    add(f"\nMonths too recent to have 6 later months (May to October 2026) are checked against the 12 months "
        f"before only: {len(recent)} flagged. Weeks inside the snapshot (`sql/weekly_spikes.sql`, the same rule "
        f"against the 8 weeks before and after, at least {M.WEEK_MIN_EXCESS} above): none flagged; the highest "
        f"was {short(wmax['product']).lower()} in the week of {pd.Timestamp(wmax['week']).day} "
        f"{pd.Timestamp(wmax['week']):%B %Y}, "
        f"{wmax['r']:.2f} times its baseline.\n")

    add("## 3. Growth, with and without the spikes\n")
    add("![Growth with and without spikes](charts/07_growth_with_and_without_spikes.png)\n")
    add("Spike months set to their baseline (the larger of the two medians); every other month as counted. "
        "FY2019 is the first year after the April 2017 product list settled.\n")
    add(md_table(pd.DataFrame({
        "Product": gr["current_product"].map(short),
        "FY2025": gr["fy2025"].map(n), "FY2026": gr["fy2026"].map(n),
        "Change": gr["change_1y"].map(signed),
        "Change without spikes": gr["change_1y_adjusted"].map(signed),
        "FY2019 to FY2026": gr["change_7y"].map(lambda x: f"{x + 1:.1f}x"),
        "Without spikes": gr["change_7y_adjusted"].map(lambda x: f"{x + 1:.1f}x"),
    }), "lrrrrrr"))
    add("\nFY2019 and FY2026 have no spike months, so the seven-year multiples are the same either way. "
        "The money-transfer multiple is large because the product had few complaints in FY2019.\n")

    add("## 4. Who is behind the FY2026 growth\n")
    add("Average complaints per month in FY2025 and FY2026 over each product's non-spike months, split by "
        "company (`sql/fy_change_by_company.sql`; company changes add up exactly to the product's change). "
        "\"Largest share\" is the part of the change from the single company that moved most, shown only "
        "where the product changed by at least 5%.\n")
    dd = drv.copy()
    big = (dd["change_per_month"].abs() >= 0.05 * dd["per_month_2025"])
    add(md_table(pd.DataFrame({
        "Product": dd["current_product"].map(short),
        "Per month FY2025": dd["per_month_2025"].map(n), "Per month FY2026": dd["per_month_2026"].map(n),
        "Companies up / down": [f"{n(a)} / {n(b)}" for a, b in zip(dd["companies_up"], dd["companies_down"])],
        "Largest share": [pct(x, 0) if b else "-" for x, b in zip(dd["lead_share"], big)],
        "Companies that added most (complaints per month)": dd["top_companies"],
    }), "lrrrrl"))
    rising = dd[big & (dd["current_product"] != T.CREDIT_REPORTING)].sort_values("lead_share", ascending=False)
    biggest = rising.iloc[0]
    others_under_half = bool((rising["lead_share"].iloc[1:] < 0.5).all())
    more_up = int((dd["companies_up"] > dd["companies_down"]).sum())
    add(f"\nOutside credit reporting, the most concentrated rise is {short(biggest['current_product']).lower()}: "
        f"{biggest['lead_company']} made up {pct(biggest['lead_share'], 0)} of it. "
        + ("In every other product that rose by 5% or more, the largest single company is under half of the change. "
           if others_under_half else "")
        + f"In {of(more_up, len(dd))} products more companies gained complaints than lost them. "
        "For a company, that means a rise in its own complaints in FY2026 is more likely part of a market-wide "
        "trend than a problem of its own; Part 3 checks this against peers.\n")

    add("## 5. What FY2026 complaints are about\n")
    add("![Top issue by product](charts/08_top_issue_by_product.png)\n")
    add("The three most common issues in each product (`sql/issue_mix.sql`; all issues in "
        "`results/issue_mix_fy2026.csv`):\n")
    add(md_table(pd.DataFrame({
        "Product": top3["product"].map(short), "#": top3["rank"], "Issue": top3["issue"],
        "Complaints": top3["complaints"].map(n), "Share of product": top3["share"].map(pct),
    }), "lrlrr"))
    add("\nRead as a to-do list, the top issues point at different teams: disputed debts and debt validation "
        "(debt collection), purchase disputes on statements (credit cards), account management (bank accounts), "
        "fraud and scams (money transfers), payment processing (mortgages) and servicing (student loans).\n")

    add("## 6. Do the repeats or the two-way spellings change anything?\n")
    add(f"Company names that differ only in case, spaces or punctuation are merged under their most common "
        f"spelling (`sql/company_names.sql`): {rob['merged_companies']} companies, {n(rob['merged_complaints'])} "
        f"FY2026 complaints. The figures below use merged names, with and without the "
        f"{n(rob['products']['complaints'].sum() - rob['products']['complaints_no_repeats'].sum())} repeats "
        "(complaints identical to an earlier one on every field except the ID).\n")
    add(md_table(pd.DataFrame([
        ["Companies", n(wi["companies"]), n(wo["companies"])],
        ["Top-10 share", pct(wi["top10_share"]), pct(wo["top10_share"])],
        ["Companies for half of all complaints", n(wi["companies_for_half"]), n(wo["companies_for_half"])],
        ["Companies with one complaint", n(wi["single_complaint_companies"]), n(wo["single_complaint_companies"])],
        ["Debt collection share", pct(rob["products"].set_index("product").loc[T.DEBT_COLLECTION, "share"]),
         pct(rob["products"].set_index("product").loc[T.DEBT_COLLECTION, "share_no_repeats"])],
    ], columns=["Figure", "With repeats", "Without repeats"]), "lrr"))
    add(f"\nProduct order and every product's top issue are the same without the repeats; the largest move in "
        f"an issue's share is {pct(rob['max_issue_share_shift'], 1).replace('%', '')} percentage points. The top 10 "
        "companies are the same 10, but the order at the top depends on the repeats:\n")
    add(md_table(pd.DataFrame({
        "Company": t10["company"], "Rank": t10["rank"], "Rank without repeats": t10["rank_no_repeats"],
    }), "lrr"))
    mv = "; ".join(f"{c} {pct(rep_rate[c])} (rank {a} to {b})" for c, a, b in
                   zip(movers["company"], movers["rank"], movers["rank_no_repeats"]))
    add(f"\nThe companies that drop furthest have more repeats than the snapshot's {pct(all_rate)}: {mv}. That fits "
        "one person disputing several debts on the same day, but the data cannot tell that apart from a "
        "duplicate. A ranking of companies by raw count should say whether repeats are in it.\n")

    add("## 7. What this means for the business\n")
    add("1. **Check for a spike before reading any year-on-year change.** One month at one company can turn "
        "growth into an apparent 50% fall. Report changes with and without spike months, as here.")
    add(f"2. **When a spike comes, look for the company first.** In {of(two_firms, len(sp))} spikes the two largest "
        "companies make up half or more of the extra complaints, and some spikes match public events about the "
        "company (an enforcement action, a data breach). A complaints team should be ready for a surge after "
        "public news about its own firm.")
    add(f"3. **FY2026 growth is broad, not one firm's.** In {of(more_up, len(dd))} products more companies gained "
        "complaints than lost them, so a company whose complaints rose in line with its market may not have a "
        "problem of its own; Part 3 compares companies with their peers.")
    add(f"4. **Start root-cause work with the top issue.** In {len(quarter)} of {len(top1)} products the most "
        f"common issue is a quarter or more of complaints (up to {pct(top1['share'].max(), 0)}).")
    add("5. **Say whether repeats are counted** when ranking companies, especially debt collectors.")
    return "\n".join(L) + "\n"


def write(out: Path = RESULTS) -> str:
    out.mkdir(parents=True, exist_ok=True)
    report = build_report(out)
    (out / REPORT).write_text(report)
    return report


def main() -> int:
    report = write()
    print(f"wrote results/{REPORT} ({len(report.splitlines())} lines), 8 CSVs and 4 charts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
