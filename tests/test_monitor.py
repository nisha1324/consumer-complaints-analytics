"""Part 4: the early-warning monitor.

First the alert rule and the episode logic on hand-made weeks, then the two SQL monitors on a
hand-made snapshot, then the committed data against an independent pandas version.
"""
from __future__ import annotations

from datetime import timedelta

import duckdb
import numpy as np
import pandas as pd
import pytest

from complaints import build, load, monitor as M, source
from scripts import monitor_report
from tests.conftest import bulk_row, write_bulk

RESULTS = source.ROOT / "results"
DC = "Debt collection"
A, B = "Attempts to collect debt not owed", "Written notification about debt"
W = M.weeks()


# ---------------------------------------------------------------- the rule and episodes, by hand

def _grid(rows):
    """rows: (company, issue, week index, complaints, baseline, after_median, repeats)."""
    return pd.DataFrame([{"company": c, "product": DC, "issue": i, "week": W[k], "complaints": n,
                          "baseline": b, "after_median": a, "repeats": r} for c, i, k, n, b, a, r in rows])


def test_flag_edges():
    g = M.flag(_grid([
        ("X", A, 8, 40, 20.0, 5.0, 0),     # exactly 2x and exactly 20 above: alert
        ("X", A, 9, 39, 19.5, 5.0, 0),     # 2x but 19.5 above: no
        ("X", A, 10, 25, 4.0, 5.0, 0),     # 6x but 21 above: alert
        ("X", A, 11, 99, 50.0, 5.0, 0),    # 49 above but under 2x: no
        ("X", A, 12, 99, np.nan, 5.0, 0),  # no baseline yet: never an alert
        ("X", A, 13, 20, 0.0, 5.0, 0),     # from nothing to 20: alert
    ]))
    assert g["alert"].tolist() == [True, False, True, False, False, True]
    # looser rule: 39 >= 1.5 x 19.5 and 19.5 above; 99 >= 1.5 x 50 and 49 above
    assert M.flag(g, 1.5, 10)["alert"].tolist() == [True, True, True, True, False, True]


def test_episodes_shared_and_items():
    g = M.flag(_grid([
        ("X", A, 8, 40, 10.0, 30.0, 4),     # X/A: weeks 8, 9 one episode; week 11 a new one
        ("X", A, 9, 50, 10.0, 15.0, 6),
        ("X", A, 11, 40, 10.0, np.nan, 0),
        ("Y", A, 9, 30, 5.0, 4.0, 0),       # Y/A alerts in week 9 too: X's first episode and Y's are shared
        ("Y", B, 8, 30, 5.0, 4.0, 30),      # alone on B
        ("Z", A, 10, 1, 5.0, 4.0, 0),       # no alert
    ]))
    a = M.alerts(g)
    assert len(a) == 5 and a["new_episode"].sum() == 4
    e = M.episodes(a).set_index(["company", "issue", "start"])
    x1 = e.loc[("X", A, W[8])]
    assert x1["weeks"] == 2 and x1["complaints"] == 90 and x1["excess"] == 70 and x1["peak"] == 50
    assert x1["shared"] and x1["companies_on_issue"] == 2           # shared in its second week only
    assert x1["after"] == "fell back"                               # 15 < 2 x 10 (the first week's baseline)
    assert x1["repeat_share"] == pytest.approx(10 / 90)
    assert e.loc[("X", A, W[11])]["after"] == "too recent" and not e.loc[("X", A, W[11])]["shared"]
    assert e.loc[("Y", B, W[8])]["after"] == "fell back" and not e.loc[("Y", B, W[8])]["shared"]
    it = M.items(M.episodes(a))
    # week 8: X/A and Y/B (different issues: 2 items); week 9: Y/A; week 11: X/A
    assert it.groupby("start").size().to_dict() == {W[8]: 2, W[9]: 1, W[11]: 1}
    pw = M.per_week(M.episodes(a), pd.DataFrame({"start": [W[9], W[20]]}))
    assert pw["total"].sum() == 4 + 2
    assert pw.set_index("week").loc[W[9], ["shared_surges", "outcome_shifts"]].tolist() == [1, 1]


def test_surge_detection_is_exact():
    g = M.flag(_grid([("X", A, 8, 10, 10.0, 0, 0), ("X", A, 9, 5, 4.0, 0, 0), ("X", A, 10, 60, 50.0, 0, 0)]))
    d = M.surge_detection(g, surges=(1.0, 2.0)).set_index("baseline_band")
    # 10 + 10 = 20: 2x but only 10 above -> no; 10 + 20 = 30: 20 above -> yes
    assert d.loc["10-19", "caught_1x"] == 0 and d.loc["10-19", "caught_2x"] == 1
    assert d.loc["1-4", "caught_2x"] == 0                    # 5 + 8 = 13: only 9 above
    assert d.loc["50+", "caught_1x"] == 1                    # 110 >= 100 and 60 above
    assert np.isnan(d.loc["5-9", "caught_1x"]) and d.loc["5-9", "series_weeks"] == 0


# ---------------------------------------------------------------- the SQL on a hand-made snapshot

def _day(k: int, offset: int = 0) -> str:
    return (W[k].to_pydatetime() + timedelta(days=offset)).strftime("%Y-%m-%d")


def _toy_rows() -> list[dict]:
    rows, cid = [], iter(range(1, 100_000))

    def add(company, issue, k, n, response="Closed with explanation", timely="Yes", repeat=False):
        first = None
        for j in range(n):
            z = first if (repeat and first) else f"{next(cid):05d}"
            first = first or z
            rows.append(bulk_row(next(cid), received=_day(k, j % 7), product=DC, sub_product="Other debt",
                                 issue=issue, sub_issue="", company=company, response=response, timely=timely,
                                 zip_code=z))
    # X on A: 10 a week for weeks 0-7 except week 3 (none), then 40 in week 8 and 10 again
    for k in range(0, 13):
        if k != 3:
            add("X LLC", A, k, 40 if k == 8 else 10)
    # X on B: 2 a week, then a week of 30 identical repeats (same day/zip/etc.) in week 9
    for k in range(0, 13):
        add("X LLC", B, k, 2)
    rows.extend(bulk_row(next(cid), received=_day(9), product=DC, sub_product="Other debt", issue=B, sub_issue="",
                         company="X LLC", zip_code="99999") for _ in range(30))
    # Y: relief outcome monitor. 20 final responses a week for 20 weeks: no relief in weeks 0-15,
    # all relief from week 16; one complaint still in progress in week 16 (left out).
    for k in range(20):
        add("Y INC", A, k, 20, "Closed with non-monetary relief" if k >= 16 else "Closed with explanation")
    add("Y INC", A, 16, 1, "In progress")
    return rows


@pytest.fixture(scope="module")
def toy(tmp_path_factory):
    d = tmp_path_factory.mktemp("toy4")
    csv_path = write_bulk(d / "c.csv", _toy_rows())
    build.build(csv_path, d / "s.parquet", d / "m.csv")
    hist = pd.DataFrame({"month": ["2026-01"] * 2, "product": [DC] * 2, "sub_product": ["Other debt"] * 2,
                         "company": ["X LLC", "Y INC"], "complaints": [1, 1]})
    comp = d / "company.parquet"
    duckdb.register("h", hist)
    duckdb.execute(f"COPY (SELECT month, product, sub_product, company, CAST(complaints AS BIGINT) AS complaints "
                   f"FROM h) TO '{comp}' (FORMAT parquet)")
    duckdb.unregister("h")
    con = load.connect(d / "s.parquet", d / "m.csv", comp)
    from complaints import response as R
    R.prepare(con)
    return con


def test_toy_volume_grid(toy):
    g = M.flag(M.volume(toy))
    xa = g[(g["company"] == "X LLC") & (g["issue"] == A)].set_index("week")
    assert len(xa) == len(W)                                  # full grid, missing weeks are 0
    assert xa.loc[W[3], "complaints"] == 0 and xa.loc[W[20], "complaints"] == 0
    assert xa["baseline"].iloc[:8].isna().all()               # needs all 8 weeks before
    assert xa.loc[W[8], "baseline"] == 10                     # median of 10 x7 and 0 -> 10
    assert xa.loc[W[8], "alert"] and xa["alert"].sum() == 1
    assert xa.loc[W[8], "after_median"] == 10                 # weeks 9-12
    assert np.isnan(xa.loc[W[-1], "after_median"])
    xb = g[(g["company"] == "X LLC") & (g["issue"] == B)].set_index("week")
    assert xb.loc[W[9], "complaints"] == 32 and xb.loc[W[9], "repeats"] == 29 and xb.loc[W[9], "alert"]
    # without the repeats week 9 has 3 complaints and no alert
    nr = M.flag(M.volume(toy, where="NOT is_repeat"))
    assert not nr.loc[(nr["company"] == "X LLC") & (nr["issue"] == B), "alert"].any()


def test_toy_outcome_windows(toy):
    o = M.outcomes(toy, "relief")
    assert set(o["company"]) == {"X LLC", "Y INC"}            # both have 100+ final responses
    y = o[o["company"] == "Y INC"].set_index("week")
    assert y["before_n"].iloc[:M.RECENT + M.BEFORE - 1].isna().all()
    r = y.loc[W[16]]                                          # recent = weeks 13-16, before = weeks 1-12
    assert r["recent_n"] == 80 and r["recent_k"] == 20 and r["before_n"] == 240 and r["before_k"] == 0
    assert r["shift"] == pytest.approx(0.25) and r["alert"]
    assert not y.loc[W[15], "alert"]
    assert y.loc[W[19], "recent_rate"] == 1 and y.loc[W[19], "before_rate"] == 0
    p = 20 / 320
    assert r["z"] == pytest.approx(0.25 / np.sqrt(p * (1 - p) * (1 / 80 + 1 / 240)))
    e = M.outcome_episodes(o)
    assert len(e) == 1 and e.iloc[0]["start"] == W[16] and e.iloc[0]["direction"] == "up"
    lag = M.detection_lag(o, "Y INC")
    assert lag["change_week"] == W[16] and lag["first_alert"] == W[16] and lag["lag_weeks"] == 0
    late = M.outcomes(toy, "late")
    assert late["alert"].sum() == 0
    with pytest.raises(ValueError):
        M.outcomes(toy, "monetary")


# ---------------------------------------------------------------- the committed data

@pytest.fixture(scope="module")
def con():
    return M.connect()


@pytest.fixture(scope="module")
def grid(con):
    return M.flag(M.volume(con))


@pytest.fixture(scope="module")
def flagged(con):
    d = con.execute("SELECT company_merged AS company, product, issue, date_received, is_repeat, company_response, "
                    "relief, late FROM responses").df()
    d["week"] = pd.to_datetime(d["date_received"]) - pd.to_timedelta(pd.to_datetime(d["date_received"]).dt.weekday,
                                                                      unit="D")
    return d


def test_volume_against_pandas(con, grid):
    d = con.execute("SELECT company_merged AS company, product, issue, date_received FROM complaints_flagged").df()
    dt = pd.to_datetime(d["date_received"])
    d["week"] = dt - pd.to_timedelta(dt.dt.weekday, unit="D")
    d = d[(d["week"] >= W[0]) & (d["week"] <= W[-1])]
    counts = d.groupby(M.SERIES + ["week"]).size()
    series = counts.reset_index()[M.SERIES].drop_duplicates()
    assert len(series) == grid[M.SERIES].drop_duplicates().shape[0]
    full = counts.unstack("week", fill_value=0).reindex(columns=W, fill_value=0)
    base = full.T.shift(1).rolling(M.WARMUP).median().T          # median of the 8 weeks before
    g = grid.set_index(M.SERIES + ["week"])
    stacked = full.stack()
    assert (g["complaints"].reindex(stacked.index) == stacked).all()
    b = base.stack(future_stack=True).reindex(g.index)
    assert np.allclose(g["baseline"], b, equal_nan=True)
    alert = (b.notna() & (stacked.reindex(g.index) >= 2 * b) & (stacked.reindex(g.index) - b >= 20))
    assert (g["alert"] == alert).all()


def test_volume_totals(grid):
    a = M.alerts(grid)
    e = M.episodes(a)
    s = M.volume_summary(grid, a, e)
    assert s["complaints"] == 644_768                         # the full weeks inside FY2026
    assert e["weeks"].sum() == s["alerts"] and e["complaints"].sum() == s["alert_complaints"]
    assert s["stayed_high"] + s["fell_back"] + s["too_recent"] == s["episodes"]
    assert (e["start"] >= M.monitored_weeks()[0]).all()
    assert M.items(e)["companies"].sum() == len(e)


def test_outcomes_against_pandas(con, flagged):
    o = M.outcomes(con, "late")
    d = flagged[(flagged["week"] >= W[0]) & (flagged["week"] <= W[-1])]
    big = d.groupby("company").size()
    assert set(o["company"]) == set(big[big >= M.MIN_RESPONSES].index)
    c = "MOHELA"
    m = d[d["company"] == c].groupby("week").agg(n=("late", "size"), k=("late", "sum")).reindex(W, fill_value=0)
    x = o[o["company"] == c].set_index("week")
    k = 20
    rec, bef = m.iloc[k - M.RECENT + 1:k + 1], m.iloc[k - M.RECENT - M.BEFORE + 1:k - M.RECENT + 1]
    assert len(bef) == M.BEFORE
    assert x.loc[W[k], "recent_n"] == rec["n"].sum() and x.loc[W[k], "recent_k"] == rec["k"].sum()
    assert x.loc[W[k], "before_n"] == bef["n"].sum() and x.loc[W[k], "before_k"] == bef["k"].sum()


def test_part3_shifts_are_caught(con):
    from complaints import response as R
    sh = R.shifts(R.halves(con))
    oe = M.outcome_episodes(M.outcomes(con, "relief"))
    assert set(sh["company"]) <= set(oe["company"])
    lag = M.detection_lag(M.outcomes(con, "relief"), "CL Holdings LLC")
    assert lag["change_week"] == pd.Timestamp("2026-04-27") and lag["lag_weeks"] == 1


def test_surge_detection_on_real_data(grid):
    """Plant the surge for real in a sample of weeks and rerun the rule: same answer as the table's shortcut."""
    d = grid[grid["baseline"].notna() & (grid["baseline"] >= 1) & ~grid["alert"]].sample(2000, random_state=1)
    for s in M.SURGES:
        planted = d.assign(complaints=d["complaints"] + s * d["baseline"])
        rerun = M.flag(planted)["alert"]
        x = d["complaints"] + s * d["baseline"]
        assert (rerun == ((x >= M.RATIO * d["baseline"]) & (x - d["baseline"] >= M.MIN_EXCESS))).all()
    det = M.surge_detection(grid)
    assert det["series_weeks"].sum() == len(grid[grid["baseline"].notna() & (grid["baseline"] >= 1) & ~grid["alert"]])
    # bigger surges are caught at least as often
    assert (det["caught_4x"] >= det["caught_2x"]).all() and (det["caught_2x"] >= det["caught_1x"]).all()


def test_repeats_check(con, grid):
    e = M.episodes(M.alerts(grid))
    rc = M.repeats_check(con, e)
    assert rc["survive"] + len(rc["lost"]) == len(e)
    assert rc["lost_repeat_share"] > rc["kept_repeat_share"]


def test_report_regenerates_byte_for_byte(tmp_path):
    monitor_report.write(tmp_path)
    produced = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    assert len(produced) == 1 + 7 + 3
    for rel in produced:
        assert (tmp_path / rel).read_bytes() == (RESULTS / rel).read_bytes(), rel


def test_detection_lag_compares_each_week_with_the_weeks_before():
    """The change week is the first week whose own rate is 20+ points from the before-window rate;
    here week 2's rate (25%) equals its recent-window rate, so only the before window can flag it."""
    o = pd.DataFrame({"company": "Q", "metric": "relief", "week": W[:4], "n": [100] * 4, "k": [0, 5, 25, 30],
                      "before_rate": [np.nan, 0.0, 0.0, 0.0], "recent_rate": [np.nan, 0.05, 0.25, 0.30],
                      "alert": [False, False, False, True]})
    lag = M.detection_lag(o, "Q")
    assert lag["change_week"] == W[2] and lag["first_alert"] == W[3] and lag["lag_weeks"] == 1
