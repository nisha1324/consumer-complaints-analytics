"""Part 4: write results/EARLY_WARNING_MONITOR.md, its CSVs and charts 13-15 from the committed data.

    python scripts/monitor_report.py
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from complaints import monitor as M, response as R  # noqa: E402
from scripts.profile_report import BLUE, INK, INK_2, MUTED, ORANGE, SAVE, SURFACE, md_table, n, pct  # noqa: E402
from scripts.response_report import DARK_BLUE, LIGHT_BLUE, _clean, pp  # noqa: E402
from scripts.sources_report import short  # noqa: E402

RESULTS = ROOT / "results"
REPORT = "EARLY_WARNING_MONITOR.md"
FSA = "Servicer under contract with Federal Student Aid"
# the three example series in chart 14: one company alone, one driven by repeats, one shared
BUREAU_SHORT = {"EQUIFAX, INC.": "Equifax", "Experian Information Solutions Inc.": "Experian",
                "TRANSUNION INTERMEDIATE HOLDINGS, INC.": "TransUnion"}
EXAMPLES = [
    ("Rocket Mortgage, LLC", "Mortgage", "Trouble during payment process"),
    (FSA, "Debt collection", "Took or threatened to take negative or legal action"),
    ("Experian Information Solutions Inc.", "Credit card", "Incorrect information on your report"),
]


def day(t: pd.Timestamp) -> str:
    return f"{t.day} {t:%b %Y}"


def wk(t: pd.Timestamp) -> str:
    """A week by its Monday."""
    return f"w/c {t.day} {t:%b}"


def rate_change(metric: str, direction: str) -> str:
    if metric == "late":
        return "more late" if direction == "up" else "fewer late"
    return "more relief" if direction == "up" else "less relief"


# ---------------------------------------------------------------- charts

def chart_per_week(pw: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4.4))
    x = pw["week"]
    bottom = np.zeros(len(pw))
    for col, color, label in (("company_surges", DARK_BLUE, "Surge at one company"),
                              ("shared_surges", LIGHT_BLUE, "Surge shared with another company"),
                              ("outcome_shifts", ORANGE, "Shift in relief or late rate")):
        ax.bar(x, pw[col], bottom=bottom, width=5.2, color=color, edgecolor=SURFACE, linewidth=1, label=label)
        bottom += pw[col].to_numpy()
    ax.yaxis.set_major_locator(mticker.MultipleLocator(1))
    ax.set_ylim(0, pw["total"].max() + 1)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    _clean(ax, "y")
    ax.set_ylabel("New items that week")
    ax.legend(frameon=False, loc="upper right", fontsize=8.5)
    quiet = int((pw["total"] == 0).sum())
    fig.suptitle(f"About {pw['total'].mean():.1f} new items a week, at most {pw['total'].max()}, and {quiet} "
                 f"quiet weeks of {len(pw)}", x=0.012, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.885, "What the monitor would have sent each week of FY2026 (week starting Monday). Surges that "
             "start in the same week on the same\nproduct and issue are one item. The outcome monitor needs 16 weeks "
             f"of history, so its first possible alert is {wk(pw['week'][pw['week'] >= M.weeks()[M.RECENT + M.BEFORE - 1]].iloc[0])}.",
             fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def _threshold(b: pd.Series) -> pd.Series:
    return np.maximum(M.RATIO * b, b + M.MIN_EXCESS)


def chart_examples(grid: pd.DataFrame, grid_nr: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 5), sharex=True)
    titles = ["One company: a new level", "Mostly identical repeats", "Shared with other companies"]
    for ax, (c, p, i), title in zip(axes, EXAMPLES, titles):
        s = grid[(grid["company"] == c) & (grid["product"] == p) & (grid["issue"] == i)].sort_values("week")
        ax.plot(s["week"], s["complaints"], color=BLUE, linewidth=2, label="Complaints that week")
        ax.step(s["week"], _threshold(s["baseline"]), where="mid", color=MUTED, linewidth=1.3, linestyle="--",
                label="Alert level (from the 8 weeks before)")
        if c == FSA:
            r = grid_nr[(grid_nr["company"] == c) & (grid_nr["product"] == p) & (grid_nr["issue"] == i)] \
                .sort_values("week")
            ax.plot(r["week"], r["complaints"], color=LIGHT_BLUE, linewidth=2, label="Without identical repeats")
        a = s[s["alert"]]
        ax.scatter(a["week"], a["complaints"], s=42, color=ORANGE, edgecolor=SURFACE, linewidth=1.2, zorder=4,
                   label="Alert")
        ax.set_title(f"{title}\n{c}\n" + textwrap.fill(f"{short(p)}: {i.lower()}", 52), loc="left",
                     fontsize=8.8, color=INK)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(10, 1, 4, 7)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
        ax.set_ylim(0, None)
        _clean(ax, "y")
    axes[0].set_ylabel("Complaints per week")
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="upper left", bbox_to_anchor=(0.008, 0.925), ncol=4, fontsize=8.5)
    fig.suptitle("Three kinds of alert", x=0.012, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.87))
    fig.savefig(path, **SAVE)
    plt.close(fig)


def chart_outcome(lag: dict, path: Path) -> None:
    d = lag["weekly"]
    fig, ax = plt.subplots(figsize=(10.5, 4.8))
    ax.plot(d["week"], 100 * d["week_rate"], color=BLUE, linewidth=2, marker="o", markersize=4,
            label="Relief rate, week received")
    ax.plot(d["week"], 100 * d["before_rate"], color=MUTED, linewidth=1.6, linestyle="--",
            label=f"The {M.BEFORE} weeks before the latest {M.RECENT}")
    a = d[d["alert"]]
    ax.scatter(a["week"], 100 * a["week_rate"], s=46, color=ORANGE, edgecolor=SURFACE, linewidth=1.2, zorder=4,
               label="Monitor alert")
    fa, ch = lag["first_alert"], lag["change_week"]
    y = 100 * float(d.loc[d["week"] == fa, "week_rate"].iloc[0])
    ax.annotate(f"First alert, {wk(fa)}\n(the change began {wk(ch)})", (fa, y), xytext=(-150, -14),
                textcoords="offset points", fontsize=8.5, color=INK,
                arrowprops={"arrowstyle": "-", "color": INK_2, "linewidth": 0.8})
    ax.set_ylim(-3, 103)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:.0f}%"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    _clean(ax, "y")
    ax.set_ylabel("Final responses closed with relief")
    ax.legend(frameon=False, loc="center left", fontsize=8.5)
    fig.suptitle(f"The outcome monitor catches {lag['company']}'s change {lag['lag_weeks']} week after it begins",
                 x=0.012, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.text(0.012, 0.875, f"Alert: the latest {M.RECENT} weeks' rate is {100 * M.SHIFT_MIN:.0f}+ points from the "
             f"{M.BEFORE} weeks before them and beyond the 99.8% chance limit.\nAlerts continue while the old "
             "rate is still in the comparison window.", fontsize=9, color=INK_2)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    fig.savefig(path, **SAVE)
    plt.close(fig)


# ---------------------------------------------------------------- report

def build_report(out: Path = RESULTS) -> str:
    charts = out / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    con = M.connect()
    base = M.volume(con)
    grid = M.flag(base)
    a = M.alerts(grid)
    e = M.episodes(a)
    it = M.items(e)
    vs = M.volume_summary(grid, a, e)
    sens = M.sensitivity(base)
    det = M.surge_detection(grid)
    grid_nr = M.flag(M.volume(con, where="NOT is_repeat"))
    rc = M.repeats_check(con, e)
    o = pd.concat([M.outcomes(con, m) for m in M.METRICS], ignore_index=True)
    oe = M.outcome_episodes(o)
    os_ = M.outcome_summary(o, oe)
    h = R.halves(con)
    sh = R.shifts(h)
    lead = h.iloc[0]["company"]
    lag = M.detection_lag(o, lead)
    pw = M.per_week(e, oe)

    chart_per_week(pw, charts / "13_monitor_items_per_week.png")
    chart_examples(grid, grid_nr, charts / "14_monitor_examples.png")
    chart_outcome(lag, charts / "15_outcome_monitor_relief.png")

    csv = {"index": False, "lineterminator": "\n", "float_format": "%.6f", "date_format": "%Y-%m-%d"}
    e.to_csv(out / "monitor_volume_episodes.csv", **csv)
    it.to_csv(out / "monitor_volume_items.csv", **csv)
    oe.to_csv(out / "monitor_outcome_episodes.csv", **csv)
    pw.to_csv(out / "monitor_items_per_week.csv", **csv)
    sens.to_csv(out / "monitor_sensitivity.csv", **csv)
    det.to_csv(out / "monitor_surge_detection.csv", **csv)
    rc["lost"].to_csv(out / "monitor_repeat_driven_episodes.csv", **csv)

    # figures used in the text
    mw = M.monitored_weeks()
    items_total = int(pw["total"].sum())
    per_company = (pd.concat([e[["company"]].assign(kind="volume"), oe[["company"]].assign(kind="outcome")])
                   .groupby("company").size().sort_values(ascending=False, kind="stable"))
    top_co, top_k = per_company.index[0], int(per_company.iloc[0])
    one_item = int((per_company == 1).sum())
    fsa_lost = rc["lost"][rc["lost"]["company"] == FSA]
    rocket = e[(e["company"] == EXAMPLES[0][0]) & (e["issue"] == EXAMPLES[0][2])].iloc[0]
    bureau_eps = e[e["company"].isin(BUREAU_SHORT)].sort_values(["product", "start"], ascending=[True, True])
    # the text names these two issues; fail loudly if the data no longer says so
    if set(bureau_eps["issue"]) != {"Incorrect information on your report", "Written notification about debt"}:
        raise ValueError(f"credit-bureau episodes are on other issues now: {sorted(set(bureau_eps['issue']))}")
    lost_share = (vs["episodes"] - rc["survive"]) / vs["episodes"]
    dc_share = float(e.loc[e["product"] == "Debt collection", "excess"].sum() / e["excess"].sum())
    dc_eps = int((e["product"] == "Debt collection").sum())
    judged_out = vs["series_weeks"]
    caught = {}
    for s in (sh["company"]):
        f = oe[(oe["company"] == s) & (oe["metric"] == "relief")]
        caught[s] = f["start"].min() if len(f) else pd.NaT
    all_caught = all(pd.notna(v) for v in caught.values())
    d20 = det.set_index("baseline_band")
    late_up = oe[(oe["metric"] == "late") & (oe["direction"] == "up")]
    lag_words = "next week" if lag["lag_weeks"] == 1 else f"{lag['lag_weeks']} weeks later"
    bilt = oe[(oe["company"] == "Bilt Technologies, Inc.") & (oe["metric"] == "late")]

    L: list[str] = []
    add = L.append
    add("# Part 4: an early-warning monitor\n")
    add("Generated by `scripts/monitor_report.py` from the committed data. Do not edit by hand.\n")
    add("Parts 2 and 3 looked back at the year. This part asks what a complaints or compliance team would have "
        "seen **week by week**, if a simple monitor had been running through FY2026. The monitor only uses the "
        "weeks before the one it is judging, as it would on the day it runs. It has two parts:\n")
    add(f"- **Volume:** complaints per week for every **series** (one company, product and issue; "
        f"{n(vs['series'])} series). A week alerts when it is at least {M.RATIO:g} times the median of the "
        f"{M.WARMUP} weeks before and at least {M.MIN_EXCESS} complaints above it (`sql/monitor_volume.sql`, "
        "`complaints/monitor.py`). Consecutive alert weeks are one **episode**. An alert is **shared** when "
        "another company alerts on the same product and issue in the same week.")
    add(f"- **Outcomes:** each company's relief rate and late rate in the latest {M.RECENT} weeks against the "
        f"{M.BEFORE} weeks before them, for the {os_['companies']} companies with {M.MIN_RESPONSES}+ final "
        f"responses. A company alerts when its rate moves by {100 * M.SHIFT_MIN:.0f} points or more and beyond "
        f"the 99.8% chance limit, with at least {M.RECENT_MIN} and {M.BEFORE_MIN} final responses in the two "
        "windows (`sql/monitor_outcomes.sql`).\n")
    add(f"The backtest runs over the {vs['weeks']} weeks from the week of {day(vs['first_week'])} to the week of "
        f"{day(vs['last_week'])} "
        f"(the first {M.WARMUP} full weeks of the year only build the baseline; the outcome monitor needs "
        f"{M.RECENT + M.BEFORE} weeks and starts {wk(os_['first_week'])}).\n")

    add("## Short answer\n")
    add(f"- **The workload is small.** Over {vs['weeks']} weeks the monitor would have sent {items_total} items: "
        f"{len(it)} volume surges and {os_['episodes']} outcome shifts, about {pw['total'].mean():.1f} a week, "
        f"never more than {pw['total'].max()}, with {int((pw['total'] == 0).sum())} quiet weeks. They concern "
        f"{per_company.size} companies across the whole market; {one_item} of them would have had a single item "
        f"all year, and the most for any one company is {top_k} ({top_co}).")
    add(f"- **Most surges are one-offs.** Of the {vs['episodes']} volume episodes, {vs['fell_back']} fell back "
        f"below the alert level within {M.AFTER} weeks, {vs['stayed_high']} stayed high and {vs['too_recent']} "
        f"are too recent to tell. {vs['multi_week']} lasted more than one week. Debt collection has "
        f"{dc_eps} of the {vs['episodes']} episodes and {pct(dc_share, 0)} of the extra complaints.")
    add(f"- **{pct(lost_share, 0)} of the surges do not survive without identical repeat complaints.** Without "
        f"the repeats Part 1 flagged, {vs['episodes'] - rc['survive']} of the {vs['episodes']} episodes disappear. "
        f"In those, "
        f"{pct(rc['lost_repeat_share'], 0)} of the complaints are repeats, against "
        f"{pct(rc['kept_repeat_share'], 0)} in the episodes that remain. {len(fsa_lost)} of them are the entry "
        f"\"{FSA}\", with {pct(fsa_lost['repeat_share'].min(), 0)} to {pct(fsa_lost['repeat_share'].max(), 0)} "
        "repeats.")
    add(f"- **{vs['shared_episodes']} of the {vs['episodes']} episodes are shared with another company.** "
        f"The three nationwide credit bureaus (Equifax, Experian and TransUnion) account for "
        f"{len(bureau_eps)} episodes on just two issues: \"incorrect information on your report\" filed under "
        f"credit cards (all three, from late December into January) and \"written notification about debt\" "
        "under debt collection (in January, and all three again in June and July). A shared surge is a different question for a team (something affecting the market or a whole issue) "
        "from a surge at one company.")
    add(f"- **The outcome monitor catches step changes within weeks.** It flagged {os_['relief']['episodes']} "
        f"shifts in relief ({os_['relief']['up']} up, {os_['relief']['down']} down) and "
        f"{os_['late']['episodes']} in lateness ({os_['late']['up']} more late, {os_['late']['down']} fewer). "
        f"{lead}'s change from Part 3 began in the week of {day(lag['change_week'])} and is flagged the "
        f"{lag_words}"
        f". {'All' if all_caught else 'Not all'} {len(sh)} companies whose relief Part 3 found moving between "
        "the two halves of the year are flagged, and the monitor dates each change.")
    add(f"- **Small series need a big surge to alert, by design.** In a series of 20 to 49 complaints a week, "
        f"an extra week's worth of complaints is caught {pct(d20.loc['20-49', 'caught_1x'], 0)} of the time and "
        f"twice that {pct(d20.loc['20-49', 'caught_2x'], 0)}; for series under 5 a week, even four weeks' worth "
        f"extra is caught "
        f"{pct(d20.loc['1-4', 'caught_4x'], 0)} of the time, because the {M.MIN_EXCESS}-complaint floor keeps "
        "them quiet.\n")

    add("## 1. What would have landed on the desk\n")
    add("![Items per week](charts/13_monitor_items_per_week.png)\n")
    add(f"Every volume surge and outcome shift is one **item** for a team to look at, except that surges "
        f"starting in the same week on the same product and issue are sent together. Over the "
        f"{vs['weeks']} weeks: {int(pw['company_surges'].sum())} surges at one company, "
        f"{int(pw['shared_surges'].sum())} shared, {int(pw['outcome_shifts'].sum())} outcome shifts "
        f"(`results/monitor_items_per_week.csv`).\n")
    counts = pw["total"].value_counts().sort_index()
    add(md_table(pd.DataFrame({"New items in the week": counts.index.astype(str),
                               "Weeks": counts.values.astype(int)}), "rr"))
    add(f"\nThe volume monitor judged {n(judged_out)} series-weeks ({n(vs['complaints_judged'])} complaints) and "
        f"alerted on {vs['alerts']} of them, in {vs['alert_series']} series at {vs['companies']} companies.\n")

    add("## 2. Volume surges\n")
    add("![Three kinds of alert](charts/14_monitor_examples.png)\n")
    add(f"- **One company, a new level.** {rocket['company']} on mortgage \"{rocket['issue'].lower()}\" went from a "
        f"usual {rocket['baseline']:.0f} a week to {rocket['peak']} at the peak and alerted {rocket['weeks']} weeks "
        f"running from the week of {day(rocket['start'])}. The median of the {M.AFTER} weeks after was "
        f"{rocket['after_median']:.0f}, {rocket['after_median'] / rocket['baseline']:.1f} times the old level.")
    add(f"- **Mostly repeats.** The entry \"{FSA}\" alerted on debt collection, \"took or threatened to take "
        f"negative or legal action\", in {len(fsa_lost)} episodes. "
        f"{pct(fsa_lost['repeat_share'].min(), 0)} to {pct(fsa_lost['repeat_share'].max(), 0)} of the complaints "
        "in them were identical repeats, and without the repeats none of those weeks alerts (section 4).")
    waves = []
    for (p, i), g in bureau_eps.groupby(["product", "issue"], sort=False):
        who = ", ".join(f"{BUREAU_SHORT[r.company]} from the week of {day(r.start)} ({r.weeks} "
                        f"week{'s' if r.weeks > 1 else ''})" for r in g.sort_values(["start", "company"]).itertuples())
        waves.append(f"{short(p).lower()} \"{i.lower()}\": {who}")
    add("- **Shared.** The three credit bureaus alerted on the same two issues: " + "; ".join(waves)
        + ". Complaints about credit reporting are not in the snapshot (Part 1); these are complaints against the "
          "bureaus filed under other products.\n")
    add(f"**Every volume item** (`results/monitor_volume_items.csv`; episodes with baselines and peaks in "
        f"`results/monitor_volume_episodes.csv`). \"Extra\" is complaints above the baseline, summed over the "
        f"episode; \"after\" says whether the {M.AFTER} weeks after the episode stayed at the alert level "
        "(hindsight, not used by the monitor):\n")
    rows = []
    for r in it.itertuples():
        sub = e[(e["start"] == r.start) & (e["product"] == r.product) & (e["issue"] == r.issue)]
        rows.append({"Week": wk(r.start), "Product": short(r.product), "Issue": r.issue,
                     "Companies": r.names, "Weeks": " / ".join(str(int(w)) for w in sub["weeks"]),
                     "Extra": n(r.excess), "Shared": "yes" if r.shared else "",
                     "After": " / ".join(sub["after"])})
    add(md_table(pd.DataFrame(rows), "lllllrll"))
    add("")

    add("### How the thresholds change the workload\n")
    add(f"The default is {M.RATIO:g} times the baseline and {M.MIN_EXCESS}+ above it. Looser settings bury a team; "
        f"tighter ones go quiet for most of the year (`results/monitor_sensitivity.csv`):\n")
    add(md_table(pd.DataFrame({
        "Times the baseline": sens["ratio"].map(lambda x: f"{x:g}"),
        "Complaints above it": sens["min_excess"], "Alert weeks": sens["alert_weeks"],
        "Episodes": sens["episodes"], "Companies": sens["companies"], "Items": sens["items"],
        "Items a week": sens["items_per_week_mean"].map(lambda x: f"{x:.1f}"),
        "Most in a week": sens["items_per_week_max"], "Weeks with none": sens["quiet_weeks"],
        "": np.where(sens["default"], "default", ""),
    }), "rrrrrrrrrl"))
    add("")
    add("### What size of surge it would catch\n")
    add("For every judged week that did not alert, add a surge of extra complaints worth a multiple of the "
        "series' baseline and ask whether the monitor would then alert. Adding to one week leaves its baseline "
        "unchanged, so this is exact, not simulated. Series-weeks with a baseline under 1 are left out "
        f"(`results/monitor_surge_detection.csv`):\n")
    add(md_table(pd.DataFrame({
        "Usual complaints a week": det["baseline_band"], "Series-weeks": det["series_weeks"].map(n),
        "Series": det["series"].map(n),
        **{f"+{s:g}x baseline": det[f"caught_{s:g}x"].map(lambda x: pct(x, 0)) for s in M.SURGES},
    }), "lrr" + "r" * len(M.SURGES)))
    add(f"\nAn extra week's worth is caught only about half the time even in large series, because the "
        f"rest of that week may have been below its usual level. The floor of {M.MIN_EXCESS} extra complaints is what keeps small series quiet: a series with 3 a week "
        "would need 23 to alert. That is the intended trade-off for a team watching thousands of series; a "
        "team watching its own company could lower the floor for the issues it cares about most.\n")

    add("## 3. Outcome shifts\n")
    add("![Outcome monitor on relief](charts/15_outcome_monitor_relief.png)\n")
    add(f"{lead} closed {pct(float(lag['weekly'].loc[lag['weekly']['week'] < lag['change_week'], 'k'].sum() / lag['weekly'].loc[lag['weekly']['week'] < lag['change_week'], 'n'].sum()))} "
        f"of its complaints with relief before the week of {day(lag['change_week'])}, and the monitor alerted "
        f"from the week of {day(lag['first_alert'])}. Weeks are by date received; in practice an outcome is known "
        "only once the company has responded, which the data does not date, so a live alert would come later "
        "than this.\n")
    add(f"**Part 3's four step changes, dated** (relief moved {100 * M.SHIFT_MIN:.0f}+ points between the two "
        "halves of the year):\n")
    add(md_table(pd.DataFrame({
        "Company": sh["company"], "Oct-Mar relief": sh["rate1"].map(pct), "Apr-Sep relief": sh["rate2"].map(pct),
        "First relief alert": [wk(caught[c]) if pd.notna(caught[c]) else "none" for c in sh["company"]],
    }), "lrrl"))
    add(f"\n**Every outcome shift** (`results/monitor_outcome_episodes.csv`). \"Before\" is the {M.BEFORE} weeks "
        f"before the latest {M.RECENT}; the rates are from the first alert week:\n")
    add(md_table(pd.DataFrame({
        "First week": oe["start"].map(wk), "Company": oe["company"],
        "Change": [rate_change(m, dr) for m, dr in zip(oe["metric"], oe["direction"])],
        "Before": oe["before_rate"].map(pct), "Latest 4 weeks": oe["recent_rate"].map(pct),
        "Move": oe["shift"].map(pp), "Responses (latest 4 weeks)": oe["recent_n"].map(n),
        "Weeks alerting": oe["weeks"],
    }), "lllrrrrr"))
    add(f"\nShifts go both ways. {len(late_up)} companies became late more often. That is the clearest alert, since the CFPB "
        "flags timeliness the same way for everyone"
        + (f". {bilt.iloc[0]['company']} went the other way, from {pct(bilt.iloc[0]['before_rate'], 0)} late "
           f"to {pct(bilt.iloc[0]['recent_rate'], 0)}" if len(bilt) else "")
        + ". A relief shift says that a company closes complaints differently, or records them differently; the "
          "data cannot say which (Part 3).\n")

    add("## 4. Repeats: de-duplicate before alerting\n")
    add(f"Part 1 found 17,349 complaints identical to an earlier one on every field except the ID; "
        f"{n(vs['repeats'])} of them fall in these weeks. They are {pct(vs['repeats'] / vs['complaints'])} of the "
        f"complaints in these weeks but {pct(vs['alert_repeats'] / vs['alert_complaints'])} of the complaints in "
        "alert weeks. Rerunning the "
        f"volume monitor without them, {rc['survive']} of the {vs['episodes']} episodes still alert in at least "
        f"one of their weeks and {vs['episodes'] - rc['survive']} do not "
        f"(`results/monitor_repeat_driven_episodes.csv`):\n")
    lost = rc["lost"]
    add(md_table(pd.DataFrame({
        "Week": lost["start"].map(wk), "Company": lost["company"], "Product": lost["product"].map(short),
        "Issue": lost["issue"], "Complaints": lost["complaints"].map(n),
        "Repeats": lost["repeats"].map(n), "Repeat share": lost["repeat_share"].map(lambda x: pct(x, 0)),
    }), "lllllrr"))
    add(f"\nWithout the repeats the monitor finds {rc['episodes_nr']} episodes in all. A repeat can be a consumer "
        "filing the same complaint twice, or a batch filed for several consumers; the data cannot tell which. For a "
        "team the answer is the same: count each distinct complaint once before alerting.\n")

    add("## So what for a complaints or compliance team\n")
    add(f"1. **A weekly monitor is cheap to run and to staff.** On this rule the whole market produced about "
        f"{pw['total'].mean():.1f} items a week, and no single company had more than {top_k} all year. Run it on the "
        "company's own complaints (and on the CFPB's public data, to see the market).")
    add(f"2. **Strip identical repeats first.** {vs['episodes'] - rc['survive']} of the {vs['episodes']} surges "
        "here did not survive without them; leaving them in would send a team chasing duplicates.")
    add("3. **Ask whether a surge is shared.** When competitors alert on the same issue the same week, look for "
        "a common cause (a market event, an industry-wide change, a filing campaign) before treating it as your "
        "own service failure.")
    add(f"4. **Expect most surges to fall back, and watch the ones that don't.** "
        f"{vs['episodes'] - vs['multi_week']} of the {vs['episodes']} episodes lasted one week; "
        "the few that stayed high (like Rocket Mortgage's payment-process complaints) are the ones that need a "
        "root-cause review.")
    add("5. **Monitor outcomes, not only volumes.** A step change in relief or lateness is invisible in "
        "complaint counts. The outcome monitor found every change Part 3 found, and dated it.")
    add(f"6. **Tune the thresholds to the team, not to the data.** The table in section 2 shows the trade-off: "
        f"from {sens['items_per_week_mean'].max():.1f} items a week at the loosest setting tried to "
        f"{sens['items_per_week_mean'].min():.1f} at the tightest.\n")

    add("## Limits\n")
    add(f"- One fiscal year. The monitor needs {M.WARMUP} weeks of history before it can judge a week (and the "
        f"outcome monitor {M.RECENT + M.BEFORE}), so the backtest covers {vs['weeks']} weeks, and the last "
        f"{M.AFTER} weeks' episodes cannot yet be called one-offs or new levels.")
    add("- Weeks are by date received. A live monitor sees a complaint only once the CFPB publishes it, and an "
        "outcome only once the company responds; the data has no publication or response date, so the delay "
        "cannot be measured here.")
    add("- There is no list of real incidents to score the alerts against, so the backtest measures workload "
        "and what size of surge would be caught, not how many alerts were \"right\".")
    add("- The issue is the consumer's choice from the CFPB's list, and the same problem can be filed under "
        "different issues or products (the credit bureaus' complaints above are one example).")
    add("- A rule this simple ignores weekly seasonality such as holidays; with one year of data there is no "
        "earlier year to learn it from.")
    return "\n".join(L) + "\n"


def write(out: Path = RESULTS) -> str:
    out.mkdir(parents=True, exist_ok=True)
    report = build_report(out)
    (out / REPORT).write_text(report)
    return report


def main() -> int:
    report = write()
    print(f"wrote results/{REPORT} ({len(report.splitlines())} lines), 7 CSVs and 3 charts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
