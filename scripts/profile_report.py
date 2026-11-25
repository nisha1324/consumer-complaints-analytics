"""Part 1: write results/PROFILE.md, its CSVs and charts 01-04 from the committed snapshot.

    python scripts/profile_report.py
"""
from __future__ import annotations

import json
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
from complaints import load, profile as P, source  # noqa: E402

RESULTS = ROOT / "results"

# The monthly history ends with a part month (the bulk file runs to 23 Nov 2026).
HISTORY_LAST_MONTH = "2026-10"

# Reference palette (light mode), as in Nisha's other projects
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK_2, MUTED, GRID, SURFACE, SHADE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1", "#fcfcfb", "#efeeea"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.titlecolor": INK, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "path.simplify": False, "svg.hashsalt": "cfpb",
})
SAVE = {"dpi": 150, "metadata": {"Software": None}}


def n(x: float) -> str:
    return f"{x:,.0f}"


def pct(x: float, nd: int = 1) -> str:
    return f"{100 * x:.{nd}f}%"


def thousands(x: float, _pos=None) -> str:
    if x >= 1_000_000:
        return f"{x / 1_000_000:.1f}M".replace(".0M", "M")
    return f"{x / 1000:.0f}k" if x >= 1000 else f"{x:.0f}"


def _style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def md_table(df: pd.DataFrame, align: str | None = None) -> str:
    cols = list(df.columns)
    align = align or "l" + "r" * (len(cols) - 1)
    sep = ["---:" if a == "r" else "---" for a in align]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(sep) + " |"]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


# ---------------------------------------------------------------- charts

def chart_history(split: pd.DataFrame, path: Path) -> None:
    d = split[split["month"] <= HISTORY_LAST_MONTH].copy()
    d["date"] = pd.to_datetime(d["month"] + "-01")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    panels = (("credit_reporting", "Credit reporting"), ("other_products", "All other products"))
    for ax, (col, title) in zip(axes, panels):
        ax.axvspan(pd.Timestamp(source.WINDOW_START), pd.Timestamp(source.WINDOW_END), color=SHADE, zorder=0)
        ax.plot(d["date"], d[col], color=BLUE, linewidth=2)
        ax.set_title(title, loc="left", fontsize=10.5)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(thousands))
        ax.set_ylim(0, None)
        _style(ax)
        ymax = ax.get_ylim()[1]
        ax.text((pd.Timestamp(source.WINDOW_START) - timedelta(days=20)).to_pydatetime(), ymax * 0.03, "FY2026\nsnapshot",
                fontsize=8.5, color=INK_2, va="bottom", ha="right")
    # Label the largest month of the right panel (a one-month surge, see the report).
    peak = d.loc[d["other_products"].idxmax()]
    axes[1].text((peak["date"] - timedelta(days=45)).to_pydatetime(), peak["other_products"],
                 f"{peak['date']:%B %Y}: {n(peak['other_products'])}", fontsize=9, color=INK, ha="right", va="top")
    fig.suptitle("Complaints per month sent to companies, December 2011 to October 2026",
                 x=0.012, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.875, "Each panel has its own scale. Shaded: October 2025 to September 2026, "
             "the window of the row-level snapshot.", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_products(mix: pd.DataFrame, path: Path) -> None:
    d = mix.iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.barh(d["product"], d["complaints"], color=BLUE, height=0.62)
    for y, (v, s) in enumerate(zip(d["complaints"], d["share"])):
        ax.text(v + d["complaints"].max() * 0.01, y, f"{n(v)}  ({pct(s)})", va="center", fontsize=9, color=INK)
    ax.set_xlim(0, d["complaints"].max() * 1.22)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(thousands))
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.tick_params(axis="y", labelcolor=INK)
    fig.suptitle("FY2026 complaints by product (credit reporting excluded)", x=0.012, ha="left",
                 fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.885, f"{n(mix['complaints'].sum())} complaints received 1 Oct 2025 to 30 Sep 2026; "
             "share of the snapshot in brackets.", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_concentration(conc: pd.DataFrame, summ: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.plot(conc["rank"], 100 * conc["cumulative_share"], color=BLUE, linewidth=2)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _p: n(x)))
    ax.set_ylim(0, 102)
    ax.set_xlim(1, len(conc) * 1.15)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _p: f"{y:.0f}%"))
    ax.set_xlabel("Companies, ranked by complaints (log scale)")
    ax.set_ylabel("Share of all complaints")
    _style(ax)
    marks = ((10, conc.loc[conc["rank"] == 10, "cumulative_share"].iloc[0], "top 10"),
             (summ["companies_for_half"], 0.5, "half"),
             (summ["companies_for_80"], 0.8, "80%"))
    for x, y, label in marks:
        ax.plot([x], [100 * y], "o", color=BLUE, markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
        ax.text(x * 1.25, 100 * y - 1, f"{n(x)} companies: {pct(y, 0) if label != 'top 10' else pct(y)}",
                fontsize=9, color=INK, va="top")
    fig.suptitle("A few companies draw most complaints", x=0.012, ha="left",
                 fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.885, f"FY2026 snapshot: {n(summ['companies'])} companies; "
             f"{n(summ['single_complaint_companies'])} of them have a single complaint.",
             fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_response_status(resp: pd.DataFrame, path: Path) -> None:
    d = resp.copy()
    d["date"] = [pd.Timestamp(m + "-01").to_pydatetime() for m in d["month"]]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    series = (("not_timely", "Not timely", ORANGE), ("in_progress", "Still in progress", BLUE))
    for col, label, colour in series:
        y = 100 * d[col] / d["complaints"]
        ax.plot(d["date"], y, color=colour, linewidth=2, marker="o", markersize=5, label=label)
        ax.text(d["date"].iloc[-1] + timedelta(days=8), y.iloc[-1], f"{label}\n{y.iloc[-1]:.1f}%",
                fontsize=9, color=INK, va="center")
    ax.set_xlim(d["date"].iloc[0] - timedelta(days=10), d["date"].iloc[-1] + timedelta(days=75))
    ax.set_xticks(list(d["date"].iloc[::2]))
    ax.set_ylim(0, None)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _p: f"{y:.0f}%"))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %Y"))
    ax.set_ylabel("Share of the month's complaints")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    _style(ax)
    fig.suptitle("Response status by month received, as of the snapshot", x=0.012, ha="left",
                 fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.885, "Recent months still have open complaints, so their outcomes are not final yet.",
             fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(path, **SAVE)
    plt.close(fig)


# ---------------------------------------------------------------- report

CHECK_NOTES = {
    1: "Each row is one complaint.",
    2: "The snapshot holds the window and nothing else.",
    3: "Dates are consistent.",
    4: "Time spent at the CFPB, before the company sees the complaint: not the company's delay.",
    5: "Timeliness can be read on every complaint.",
    6: "Outcome not final yet: leave these out of response-rate figures, or wait.",
    7: "The company did not respond in time.",
    8: "The company closed the complaint, but late. Count both kinds when measuring timeliness.",
    9: "The two fields agree.",
    10: "Leave out of state-level figures, or report as 'unknown'.",
    11: "The full name UNITED STATES MINOR OUTLYING ISLANDS, not a code. Map it before grouping.",
    12: "Published rule: the 5-digit ZIP is hidden where the ZIP area has under 20,000 people.",
    13: "Under the same published rule, no ZIP is shown when the 3-digit area is small too.",
    14: "No ZIP given.",
    15: "ZIP codes are clean apart from the masking above.",
    16: "Not missing data: these issues have no sub-issues. Group by issue, not sub-issue, for full coverage.",
    17: "No true gaps in sub-issue.",
    18: "Every complaint has a sub-product.",
    19: "Possible repeat filings; no consumer identifier, so they cannot be confirmed. Kept, and flagged.",
    20: "The same company spelled two ways. Merge before ranking companies.",
    21: "Count both tags when filtering by tag.",
}


def build_report(out: Path = RESULTS) -> str:
    charts = out / "charts"
    con = load.connect()
    manifest = json.loads(source.MANIFEST_PATH.read_text())
    hist = P.history(con)
    split = P.monthly_split(con)
    mix = P.product_mix(con)
    conc = P.concentration(con)
    summ = P.concentration_summary(conc)
    cols = P.column_profile(con)
    checks = P.quality_checks(con)
    resp = P.response_by_month(con)
    reps = P.repeats_by_product(con)
    names = P.name_collisions(con)
    lag = P.sending_lag(con)
    old = P.old_in_progress(con)
    total = int(mix["complaints"].sum())

    charts.mkdir(parents=True, exist_ok=True)
    chart_history(split, charts / "01_history_by_month.png")
    chart_products(mix, charts / "02_fy2026_by_product.png")
    chart_concentration(conc, summ, charts / "03_company_concentration.png")
    chart_response_status(resp, charts / "04_response_status_by_month.png")

    hist.to_csv(out / "history_by_fiscal_year.csv", index=False, lineterminator="\n")
    mix.to_csv(out / "product_mix_fy2026.csv", index=False, lineterminator="\n", float_format="%.6f")
    conc.to_csv(out / "company_ranking_fy2026.csv", index=False, lineterminator="\n", float_format="%.6f")
    cols.to_csv(out / "column_profile.csv", index=False, lineterminator="\n", float_format="%.6f")
    checks.to_csv(out / "quality_checks.csv", index=False, lineterminator="\n", float_format="%.6f")
    resp.to_csv(out / "response_by_month.csv", index=False, lineterminator="\n")

    ck = checks.set_index("check_id")["complaints"]
    fy = hist.set_index("fiscal_year")
    fy19, fy26 = fy.loc[2019], fy.loc[2026]
    dc = mix.set_index("product").loc["Debt collection"]
    not_timely = int(ck[7] + ck[8])
    rep_dc = reps.set_index("product").loc["Debt collection", "repeats"]
    sep = resp.set_index("month").loc["2026-09"]
    mohela = int(old.loc[old["company"] == "MOHELA", "complaints"].sum())
    mohela_sl = int(con.execute(
        "SELECT count(*) FROM complaints WHERE company = 'MOHELA' AND company_response = 'In progress' "
        "AND date_received < DATE '2026-08-01' AND product = 'Student loan'").fetchone()[0])
    top = conc.head(10).copy()

    L: list[str] = []
    add = L.append
    add("# Part 1: source, snapshot and data profile\n")
    add("Generated by `scripts/profile_report.py` from the committed snapshot. Do not edit by hand.\n")
    add("## Short answer\n")
    add(f"- **The database grew {fy26['complaints'] / fy19['complaints']:.0f}-fold in seven years, and credit "
        f"reporting is most of it.** "
        f"Complaints rose from {n(fy19['complaints'])} in FY2019 to {n(fy26['complaints'])} in FY2026 "
        f"(US federal fiscal years, October to September); credit reporting went from {pct(fy19['credit_reporting_share'])} "
        f"to {pct(fy26['credit_reporting_share'])} of them. Every other product together went from "
        f"{n(fy19['other_products'])} to {n(fy26['other_products'])}.")
    add(f"- **The row-level snapshot is the {n(total)} FY2026 complaints about everything except credit reporting.** "
        f"Debt collection is {pct(dc['share'])} of them; credit cards and bank accounts are next.")
    add(f"- **Complaints are concentrated.** The 10 most-complained-about companies draw {pct(summ['top10_share'])} "
        f"of complaints, {summ['companies_for_half']} companies draw half, and {n(summ['single_complaint_companies'])} "
        f"of {n(summ['companies'])} companies have one complaint each.")
    add(f"- **The data is clean where it matters, with five traps to handle before analysis:** "
        f"{n(ck[6])} complaints are still in progress ({n(sep['in_progress'])} of them from September 2026); "
        f"\"not timely\" has two forms ({n(ck[7])} with no response in time, {n(ck[8])} closed late); "
        f"{n(ck[19])} complaints ({pct(ck[19] / total)}) are identical to an earlier one on every field except the ID, "
        f"{pct(rep_dc / ck[19], 0)} of them in debt collection; {len(names['name_key'].unique())} companies appear "
        f"under two spellings; and ZIP codes are masked for small areas by design.")
    add("- **There is no free text.** The CFPB removed consumers' complaint narratives in September 2026, "
        "so every finding in this project comes from the 15 structured fields.\n")

    add("## 1. The source\n")
    add(f"- **Consumer Complaint Database**, US Consumer Financial Protection Bureau (CFPB): "
        f"<{source.DATA_PAGE}>. A US Government work, in the public domain in the United States; "
        "no key or sign-up.")
    add(f"- Bulk file `{source.BULK_URL}`, dated {manifest['bulk_last_modified']}, "
        f"{n(manifest['bulk_zip_bytes'])} bytes zipped, SHA-256 `{manifest['bulk_zip_sha256'][:16]}…`, "
        f"{n(manifest['bulk_rows'])} complaints from December 2011 to 23 November 2026, 15 columns "
        f"(field definitions: <{source.FIELDS_PAGE}>).")
    add(f"- Two 2026 changes (<{source.RELEASE_NOTES}>): narratives removed (Release 24, September 2026), "
        "and filtered CSV exports from the API capped at 100,000 complaints (Release 23, July 2026). "
        "That is why this project uses the full bulk file and not the API.")
    add("- What the CFPB says about the data: only complaints sent to companies for a response are published; "
        "complaints referred to other regulators (for example about banks and credit unions with under "
        "$10 billion in assets) are not; it is \"not a statistical sample of consumers' experiences\"; and volumes "
        "should be read against company size and market share.\n")
    add(f"Committed files (SHA-256 pinned in `complaints/source.py`; `python scripts/download_data.py` checks them):\n")
    add(md_table(pd.DataFrame([
        ["`data/complaints_fy2026.parquet`", "one row per complaint, FY2026, all products except credit reporting",
         n(manifest["snapshot_rows"])],
        ["`data/monthly_by_product.csv`", "complaints per month and product (as named when filed), full history",
         n(manifest["monthly_rows"])],
    ], columns=["File", "What", "Rows"]), "llr"))
    add(f"\nThe monthly file adds up to {n(manifest['monthly_total'])} complaints, the whole bulk file.\n")

    add("## 2. Fifteen years of complaints\n")
    add("![Complaints per month](charts/01_history_by_month.png)\n")
    h = hist[(hist["fiscal_year"] >= 2019) & (hist["fiscal_year"] <= 2026)]
    add(md_table(pd.DataFrame({
        "Fiscal year": h["fiscal_year"].map(lambda y: f"FY{y}"),
        "All complaints": h["complaints"].map(n),
        "Credit reporting": h["credit_reporting"].map(n),
        "Share": h["credit_reporting_share"].map(pct),
        "All other products": h["other_products"].map(n),
    })))
    add(f"\nFY2012 to FY2018 and the part year FY2027 are in `results/history_by_fiscal_year.csv`. "
        f"Credit-reporting complaints grew {fy26['credit_reporting'] / fy19['credit_reporting']:.0f}-fold "
        f"from FY2019 to FY2026, and all other products {fy26['other_products'] / fy19['other_products']:.1f}-fold. "
        "The data does not say why. This project keeps credit reporting out of the row-level snapshot: it is "
        "a different kind of complaint (about consumer reports, not a product the consumer chose), and at "
        f"{fy26['credit_reporting'] / 1e6:.1f} million rows in FY2026 it would swamp every other product.\n")
    surge = P.surge_month(con)
    add(f"The tall spike in the right-hand panel is {surge['month_name']}, outside the snapshot: "
        f"{n(surge['complaints'])} complaints about products other than credit reporting, against "
        f"{n(surge['prev_complaints'])} the month before and {n(surge['next_complaints'])} the month after. "
        f"Money transfers ({n(surge['mt'])} against {n(surge['mt_prev'])} the month before) and checking or "
        f"savings accounts ({n(surge['bank'])} against {n(surge['bank_prev'])}) make up {pct(surge['jump_share'], 0)} "
        "of the increase. The data does not "
        "say why. A month like this can swamp a trend, so Part 2 looks for such surges before reading any.\n")
    n_names = int(con.execute("SELECT count(DISTINCT product) FROM monthly").fetchone()[0])
    n_now = len(mix)
    add(f"Product names changed over the years: the history has {n_names} names, the FY2026 snapshot "
        f"{n_now} (plus credit reporting). Part 2 maps old names onto current ones before comparing years.\n")

    add("## 3. The FY2026 snapshot: products and companies\n")
    add("![FY2026 complaints by product](charts/02_fy2026_by_product.png)\n")
    add(md_table(pd.DataFrame({
        "Product": mix["product"], "Complaints": mix["complaints"].map(n),
        "Share": mix["share"].map(pct), "Companies": mix["companies"].map(n),
    })))
    add("\n![Company concentration](charts/03_company_concentration.png)\n")
    add(md_table(pd.DataFrame({
        "Rank": top["rank"], "Company": top["company"], "Complaints": top["complaints"].map(n),
        "Running share": top["cumulative_share"].map(pct),
    }), "rlrr"))
    add("\nThese are raw counts. Large companies have more customers, and the data has no customer counts, "
        "so a high rank is not by itself a sign of worse service. Part 3 compares companies on how they "
        "respond (shares of complaints closed with relief or answered in time), which are rates and so "
        "less tied to size.\n")

    add("## 4. Column profile\n")
    cp = cols.copy()
    cp["most_common"] = cp["most_common"].map(lambda s: (s[:60] + "…") if isinstance(s, str) and len(s) > 61 else s)
    cp.loc[cp["column_name"] == "timely_response", "most_common"] = cp.loc[
        cp["column_name"] == "timely_response", "most_common"].map({"true": "Yes", "false": "No"})
    unique = cp["distinct_values"] == cp["filled"]
    cp.loc[unique, "most_common"] = "(every value unique)"
    add(md_table(pd.DataFrame({
        "Column": cp["column_name"].map(lambda c: f"`{c}`"),
        "Filled": cp["filled_share"].map(lambda s: pct(s)),
        "Distinct": cp["distinct_values"].map(n),
        "Most common value": cp["most_common"],
        "Its share": [("" if u else pct(v)) for u, v in zip(unique, cp["most_common_share"])],
    }), "lrrlr"))
    add("\nShares of the most common value are of filled rows. `tags` and `company_public_response` are "
        "empty by design when there is no tag or the company chose not to publish a response.\n")

    add("## 5. Data-quality checks\n")
    add("Nothing is removed here: each check counts complaints, and the last column says how later parts "
        "handle it (`sql/quality_checks.sql`).\n")
    add(md_table(pd.DataFrame({
        "#": checks["check_id"], "Check": checks["check_name"], "Complaints": checks["complaints"].map(n),
        "Share": checks["share"].map(lambda s: pct(s, 2)), "What it means": checks["check_id"].map(CHECK_NOTES),
    }), "rlrrl"))
    add("")
    add(f"**Sending time.** The CFPB sends {pct(lag['same_day_share'])} of complaints to the company the day it "
        f"receives them; the median is {lag['median']} days, the 90th percentile {lag['p90']}, the 99th "
        f"{lag['p99']} and the longest {lag['max']}.\n")
    add("![Response status by month](charts/04_response_status_by_month.png)\n")
    add(f"**Open complaints.** {n(ck[6])} complaints are still in progress: {n(sep['in_progress'])} from September "
        f"2026 ({pct(sep['in_progress'] / sep['complaints'])} of that month), which is normal for recent "
        f"complaints, and {n(old['complaints'].sum())} received before August 2026, {n(mohela)} of them about "
        f"MOHELA ({n(mohela_sl)} of those about student loans). September's figures will still move as its "
        f"open complaints are answered. In total {n(not_timely)} complaints ({pct(not_timely / total)}) were "
        "not answered in time, in two forms: \"Untimely response\" and a closed response marked not timely. "
        "The CFPB's data page says that 99% of complaints sent to companies get timely responses; that headline "
        "is not broken down by product, and this snapshot leaves out credit reporting, so the two figures "
        "are not comparable.\n")
    add("**Repeats by product.**\n")
    r = reps[reps["repeats"] > 0]
    add(md_table(pd.DataFrame({
        "Product": r["product"], "Complaints": r["complaints"].map(n), "Repeats": r["repeats"].map(n),
        "Share": r["repeat_share"].map(lambda s: pct(s, 2)),
    })))
    add("\nA repeat matches an earlier complaint on date, product, issue, company, state, ZIP, tags, channel and "
        "response. Debt collection has the most, which fits one person disputing several debts with the same "
        "collector on the same day, but the data cannot tell that apart from a duplicate. They are kept, and "
        "Part 2 checks whether any finding changes without them.\n")
    add("**Company names spelled two ways.**\n")
    add(md_table(pd.DataFrame({"Company": names["company"], "Complaints": names["complaints"].map(n)})))
    add("\n## 6. What this means for the next parts\n")
    add("1. Measure response outcomes (relief, timeliness) only on complaints whose response is final; "
        "report the open ones separately.")
    add("2. Count both forms of \"not timely\".")
    add("3. Merge the company names spelled two ways before ranking companies.")
    add("4. Use issue, not sub-issue, when full coverage matters.")
    add("5. Report findings with and without the repeats where they could matter (debt collection).")
    add("6. Never rank companies on raw counts as if they were rates: the data has no customer numbers.")
    return "\n".join(L) + "\n"


def write(out: Path = RESULTS) -> str:
    out.mkdir(parents=True, exist_ok=True)
    report = build_report(out)
    (out / "PROFILE.md").write_text(report)
    return report


def main() -> int:
    report = write()
    print(f"wrote results/PROFILE.md ({len(report.splitlines())} lines), 6 CSVs and 4 charts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
