"""Part 4: an early-warning monitor, backtested on FY2026.

Two monitors, both of which only look back (each week is judged on the weeks before it, as it would
be on the day the monitor runs):

* volume (sql/monitor_volume.sql): weekly complaints per series (company x product x issue) against
  the median of the WARMUP weeks before; an alert is at least RATIO times that baseline and at least
  MIN_EXCESS complaints above it (flag()). Consecutive alert weeks of one series are one episode. An
  alert is *shared* when SHARED_MIN or more companies alert on the same product and issue in the
  same week (so not only one company's problem).
* outcomes (sql/monitor_outcomes.sql): each company's relief rate and late rate in the latest RECENT
  weeks against the BEFORE weeks before them; an alert is a move of SHIFT_MIN or more that is also
  beyond the 99.8% chance limit (Z998), with at least RECENT_MIN and BEFORE_MIN final responses in
  the two windows. Companies with MIN_RESPONSES or more final responses in the window are watched.

Weeks are full Monday-to-Sunday weeks inside the snapshot (mix.FIRST_WEEK to mix.LAST_WEEK).
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from complaints import load, mix, response as R

FIRST_WEEK, LAST_WEEK = mix.FIRST_WEEK, mix.LAST_WEEK
WARMUP = 8              # weeks of history behind every volume baseline (fixed in the SQL)
AFTER = 4               # weeks looked at afterwards to say whether a series fell back (hindsight only)
RATIO = 2.0
MIN_EXCESS = 20
SHARED_MIN = 2
SENSITIVITY = [(1.5, 10), (1.5, 20), (2.0, 10), (2.0, 20), (2.0, 50), (3.0, 20), (3.0, 50)]
SURGES = (0.5, 1.0, 2.0, 4.0)            # planted surges, as a multiple of the series' baseline
BANDS = [(1, 5), (5, 10), (10, 20), (20, 50), (50, None)]   # baseline bands (complaints a week)

RECENT, BEFORE = 4, 12
MIN_RESPONSES = R.MIN_RESPONSES
RECENT_MIN, BEFORE_MIN = 50, 100
SHIFT_MIN = R.SHIFT_MIN
Z998 = R.Z998
METRICS = ("relief", "late")

SERIES = ["company", "product", "issue"]


def connect() -> duckdb.DuckDBPyConnection:
    con = load.connect()
    R.prepare(con)
    return con


def weeks() -> pd.DatetimeIndex:
    return pd.date_range(FIRST_WEEK, LAST_WEEK, freq="7D")


def monitored_weeks() -> pd.DatetimeIndex:
    """Weeks the volume monitor can judge (the first WARMUP weeks only build the baseline)."""
    return weeks()[WARMUP:]


# ---------------------------------------------------------------- volume monitor

def volume(con: duckdb.DuckDBPyConnection, where: str = "TRUE") -> pd.DataFrame:
    """The weekly grid with each week's baseline (sql/monitor_volume.sql); flag() adds the alerts."""
    q = (load.sql("monitor_volume").replace("{first_week}", FIRST_WEEK).replace("{last_week}", LAST_WEEK)
         .replace("{where}", where))
    d = con.execute(q).df()
    d["week"] = pd.to_datetime(d["week"])
    return d


def flag(grid: pd.DataFrame, ratio: float = RATIO, min_excess: int = MIN_EXCESS) -> pd.DataFrame:
    """The alert rule: at least ratio x the baseline and at least min_excess complaints above it."""
    b, c = grid["baseline"], grid["complaints"]
    return grid.assign(alert=b.notna() & (c >= ratio * b) & (c - b >= min_excess))


def alerts(grid: pd.DataFrame, shared_min: int = SHARED_MIN) -> pd.DataFrame:
    """Alert weeks (grid from flag()) with their episode (consecutive alert weeks of one series) and
    whether shared_min or more companies alerted on the same product and issue that week."""
    a = grid[grid["alert"]].copy()
    a["excess"] = a["complaints"] - a["baseline"]
    a["companies_on_issue"] = a.groupby(["product", "issue", "week"])["company"].transform("size")
    a["shared"] = a["companies_on_issue"] >= shared_min
    a = a.sort_values(SERIES + ["week"], kind="stable")
    gap = a.groupby(SERIES, sort=False)["week"].diff()
    a["new_episode"] = gap.isna() | (gap.dt.days > 7)
    a["episode"] = a["new_episode"].cumsum()
    return a.reset_index(drop=True)


def episodes(a: pd.DataFrame, ratio: float = RATIO) -> pd.DataFrame:
    """One row per episode; shared if any of its weeks is shared. after: what the series did in the AFTER weeks after the episode's last
    week (hindsight): still at least ratio x the starting baseline, or back below it."""
    g = a.groupby("episode", sort=True)
    e = g.agg(company=("company", "first"), product=("product", "first"), issue=("issue", "first"),
              start=("week", "min"), end=("week", "max"), weeks=("week", "size"),
              baseline=("baseline", "first"), peak=("complaints", "max"), complaints=("complaints", "sum"),
              excess=("excess", "sum"), repeats=("repeats", "sum"), shared=("shared", "any"),
              companies_on_issue=("companies_on_issue", "max"), after_median=("after_median", "last"))
    e["after"] = np.select([e["after_median"].isna(), e["after_median"] >= ratio * e["baseline"]],
                           ["too recent", "stayed high"], "fell back")
    e["repeat_share"] = e["repeats"] / e["complaints"]
    return e.sort_values(["start", "excess", "company"], ascending=[True, False, True], kind="stable") \
        .reset_index(drop=True)


def items(e: pd.DataFrame) -> pd.DataFrame:
    """What a team would be sent: episodes that start in the same week on the same product and issue
    are one item (one look at the issue, however many companies it covers)."""
    return (e.groupby(["start", "product", "issue"], as_index=False)
            .agg(companies=("company", "size"), excess=("excess", "sum"), shared=("shared", "any"),
                 names=("company", lambda x: "; ".join(sorted(x))))
            .sort_values(["start", "excess"], ascending=[True, False], kind="stable").reset_index(drop=True))


def volume_summary(grid: pd.DataFrame, a: pd.DataFrame, e: pd.DataFrame) -> dict:
    mw = monitored_weeks()
    it = items(e)
    per = it.groupby("start").size().reindex(mw, fill_value=0)
    judged = grid[grid["baseline"].notna()]
    return {"series": int(grid[SERIES].drop_duplicates().shape[0]),
            "series_weeks": len(judged), "weeks": len(mw), "first_week": mw[0], "last_week": mw[-1],
            "complaints": int(grid["complaints"].sum()),
            "complaints_judged": int(judged["complaints"].sum()),
            "alerts": len(a), "episodes": len(e), "alert_series": int(a[SERIES].drop_duplicates().shape[0]),
            "companies": int(a["company"].nunique()),
            "shared_episodes": int(e["shared"].sum()), "own_episodes": int((~e["shared"]).sum()),
            "multi_week": int((e["weeks"] > 1).sum()),
            "items": len(it), "items_per_week_mean": float(per.mean()), "items_per_week_max": int(per.max()),
            "quiet_weeks": int((per == 0).sum()),
            "stayed_high": int((e["after"] == "stayed high").sum()),
            "fell_back": int((e["after"] == "fell back").sum()),
            "too_recent": int((e["after"] == "too recent").sum()),
            "excess": float(e["excess"].sum()),
            "alert_repeats": int(a["repeats"].sum()), "alert_complaints": int(a["complaints"].sum()),
            "repeats": int(grid["repeats"].sum())}


def sensitivity(grid: pd.DataFrame, settings=SENSITIVITY) -> pd.DataFrame:
    """The volume monitor at other thresholds (the baselines do not depend on them)."""
    rows = []
    for ratio, mx in settings:
        g = flag(grid, ratio, mx)
        a = alerts(g)
        e = episodes(a, ratio)
        s = volume_summary(g, a, e)
        rows.append({"ratio": ratio, "min_excess": mx, "alert_weeks": s["alerts"], "episodes": s["episodes"],
                     "series": s["alert_series"], "companies": s["companies"],
                     "shared_episodes": s["shared_episodes"], "items": s["items"],
                     "items_per_week_mean": s["items_per_week_mean"], "items_per_week_max": s["items_per_week_max"],
                     "quiet_weeks": s["quiet_weeks"], "default": ratio == RATIO and mx == MIN_EXCESS})
    return pd.DataFrame(rows)


def band_label(lo: int, hi: int | None) -> str:
    return f"{lo}+" if hi is None else f"{lo}-{hi - 1}"


def surge_detection(grid: pd.DataFrame, ratio: float = RATIO, min_excess: int = MIN_EXCESS,
                    surges=SURGES) -> pd.DataFrame:
    """If a surge of s x baseline extra complaints were added to one week of a series, would the
    monitor alert? Checked on every judged week of a series with a baseline of 1+ that did not alert
    on its own. Adding complaints to one week leaves that week's baseline unchanged, so this is exact."""
    d = grid[grid["baseline"].notna() & (grid["baseline"] >= 1) & ~grid["alert"]]
    rows = []
    for lo, hi in BANDS:
        m = (d["baseline"] >= lo) & (True if hi is None else d["baseline"] < hi)
        b, c = d.loc[m, "baseline"], d.loc[m, "complaints"]
        row = {"baseline_band": band_label(lo, hi), "series_weeks": int(m.sum()),
               "series": int(d.loc[m, SERIES].drop_duplicates().shape[0])}
        for s in surges:
            x = c + s * b
            row[f"caught_{s:g}x"] = float(((x >= ratio * b) & (x - b >= min_excess)).mean()) if m.any() else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def repeats_check(con: duckdb.DuckDBPyConnection, e: pd.DataFrame) -> dict:
    """Rerun the volume monitor without the identical repeats: which episodes survive?"""
    g = flag(volume(con, where="NOT is_repeat"))
    a2 = alerts(g)
    e2 = episodes(a2)
    # an episode survives if any of its weeks still alerts without the repeats
    ak = set(zip(a2["company"], a2["product"], a2["issue"], a2["week"]))
    survive = [any((r.company, r.product, r.issue, w) in ak for w in pd.date_range(r.start, r.end, freq="7D"))
               for r in e.itertuples()]
    e = e.assign(survives=survive)
    lost = e[~e["survives"]]
    return {"episodes": len(e), "episodes_nr": len(e2), "survive": int(e["survives"].sum()),
            "lost": lost[["company", "product", "issue", "start", "weeks", "complaints", "repeats", "repeat_share"]],
            "lost_repeat_share": float(lost["repeats"].sum() / lost["complaints"].sum()) if len(lost) else np.nan,
            "kept_repeat_share": float(e.loc[e["survives"], "repeats"].sum()
                                       / e.loc[e["survives"], "complaints"].sum())}


# ---------------------------------------------------------------- outcome monitor

def outcomes(con: duckdb.DuckDBPyConnection, metric: str = "relief") -> pd.DataFrame:
    if metric not in METRICS:
        raise ValueError(metric)
    q = (load.sql("monitor_outcomes").replace("{first_week}", FIRST_WEEK).replace("{last_week}", LAST_WEEK)
         .replace("{metric}", metric).replace("{min_responses}", str(int(MIN_RESPONSES)))
         .replace("{recent_minus_1}", str(RECENT - 1)).replace("{before_end}", str(RECENT + BEFORE - 1))
         .replace("{before}", str(BEFORE)).replace("{recent}", str(RECENT)))
    d = con.execute(q).df()
    d["week"] = pd.to_datetime(d["week"])
    d["metric"] = metric
    ok = d["before_n"].notna() & (d["recent_n"] > 0) & (d["before_n"] > 0)
    d["recent_rate"] = (d["recent_k"] / d["recent_n"]).where(ok)
    d["before_rate"] = (d["before_k"] / d["before_n"]).where(ok)
    d["shift"] = d["recent_rate"] - d["before_rate"]
    p = (d["recent_k"] + d["before_k"]) / (d["recent_n"] + d["before_n"])
    se = np.sqrt(p * (1 - p) * (1 / d["recent_n"] + 1 / d["before_n"]))
    d["z"] = (d["shift"] / se.where(se > 0)).where(ok)
    d["judged"] = ok & (d["recent_n"] >= RECENT_MIN) & (d["before_n"] >= BEFORE_MIN)
    d["alert"] = d["judged"] & (d["shift"].abs() >= SHIFT_MIN) & (d["z"].abs() > Z998)
    return d


def outcome_episodes(o: pd.DataFrame) -> pd.DataFrame:
    """Consecutive alert weeks of one company and metric are one episode; its row is the first week."""
    a = o[o["alert"]].sort_values(["metric", "company", "week"], kind="stable").copy()
    gap = a.groupby(["metric", "company"], sort=False)["week"].diff()
    a["new_episode"] = gap.isna() | (gap.dt.days > 7)
    a["episode"] = a["new_episode"].cumsum()
    e = a.groupby("episode").agg(metric=("metric", "first"), company=("company", "first"),
                                 start=("week", "min"), end=("week", "max"), weeks=("week", "size"),
                                 recent_n=("recent_n", "first"), recent_rate=("recent_rate", "first"),
                                 before_n=("before_n", "first"), before_rate=("before_rate", "first"),
                                 shift=("shift", "first"), z=("z", "first"))
    e["direction"] = np.where(e["shift"] > 0, "up", "down")
    return e.sort_values(["start", "metric", "company"], kind="stable").reset_index(drop=True)


def outcome_summary(o: pd.DataFrame, e: pd.DataFrame) -> dict:
    j = o[o["judged"]]
    first = o.loc[o["before_n"].notna(), "week"].min()
    mw = weeks()[weeks() >= first]
    per = e.groupby("start").size().reindex(mw, fill_value=0)
    out = {"companies": int(o["company"].nunique()), "judged_company_weeks": len(j),
           "first_week": first, "weeks": len(mw), "episodes": len(e),
           "companies_alerting": int(e["company"].nunique()),
           "new_per_week_mean": float(per.mean()), "quiet_weeks": int((per == 0).sum())}
    for m in METRICS:
        em = e[e["metric"] == m]
        out[m] = {"episodes": len(em), "companies": int(em["company"].nunique()),
                  "up": int((em["direction"] == "up").sum()), "down": int((em["direction"] == "down").sum())}
    return out


def detection_lag(o: pd.DataFrame, company: str, metric: str = "relief") -> dict:
    """For one company: the first week whose own rate is SHIFT_MIN or more away from the rate in the
    BEFORE weeks ahead of the window (the change), and the first week the monitor alerts."""
    d = o[(o["company"] == company) & (o["metric"] == metric)].sort_values("week").reset_index(drop=True)
    wk_rate = d["k"] / d["n"].where(d["n"] > 0)
    # the change: first week whose own rate is SHIFT_MIN+ from the before-window rate of that week
    moved = d[d["before_rate"].notna() & ((wk_rate - d["before_rate"]).abs() >= SHIFT_MIN)]
    first_alert = d.loc[d["alert"], "week"].min()
    change = moved["week"].min() if len(moved) else pd.NaT
    return {"company": company, "change_week": change, "first_alert": first_alert,
            "lag_weeks": int((first_alert - change).days // 7) if pd.notna(change) and pd.notna(first_alert) else None,
            "weekly": d.assign(week_rate=wk_rate)}


# ---------------------------------------------------------------- what lands on the desk

def per_week(ve: pd.DataFrame, oe: pd.DataFrame) -> pd.DataFrame:
    """New items a monitoring team would get each judged week: volume items (see items()), split into
    one company and shared, and outcome episodes."""
    it = items(ve)
    d = pd.DataFrame({"week": monitored_weeks()})
    d["company_surges"] = d["week"].map(it[~it["shared"]].groupby("start").size()).fillna(0).astype(int)
    d["shared_surges"] = d["week"].map(it[it["shared"]].groupby("start").size()).fillna(0).astype(int)
    d["outcome_shifts"] = d["week"].map(oe.groupby("start").size()).fillna(0).astype(int)
    d["total"] = d[["company_surges", "shared_surges", "outcome_shifts"]].sum(axis=1)
    return d
