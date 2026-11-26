-- Part 4, volume monitor: complaints per full week (Monday to Sunday) and series, where a series is
-- one company (merged name) x product x issue. Every series that has a complaint in the window gets
-- a full grid of weeks (a week with none is 0). {where} filters complaints (e.g. NOT is_repeat).
--   baseline:   median of the 8 weeks before (needs all 8): the monitor only looks back, as it
--               would on the day it runs
--   after_median: median of the 4 weeks after (needs all 4). Hindsight only, never used by the
--               alert; it says whether the series fell back or stayed high.
-- The alert rule itself (complaints against baseline) is applied in complaints/monitor.py:flag(),
-- so the thresholds can be varied without rerunning the query.
WITH weeks AS (
  SELECT CAST(w AS DATE) AS week
  FROM range(DATE '{first_week}', DATE '{last_week}' + INTERVAL 1 DAY, INTERVAL 7 DAY) t(w)
), c AS (
  SELECT company_merged AS company, product, issue, CAST(date_trunc('week', date_received) AS DATE) AS week,
         count(*) AS complaints, sum(CAST(is_repeat AS INTEGER)) AS repeats
  FROM complaints_flagged
  WHERE {where} AND date_received >= DATE '{first_week}' AND date_received < DATE '{last_week}' + INTERVAL 7 DAY
  GROUP BY ALL
), series AS (
  SELECT DISTINCT company, product, issue FROM c
), g AS (
  SELECT s.company, s.product, s.issue, w.week,
         coalesce(c.complaints, 0) AS complaints, coalesce(c.repeats, 0) AS repeats
  FROM series s CROSS JOIN weeks w
  LEFT JOIN c ON c.company = s.company AND c.product = s.product AND c.issue = s.issue AND c.week = w.week
), b AS (
  SELECT *,
         CASE WHEN count(*) OVER prior = 8 THEN median(complaints) OVER prior END AS baseline,
         CASE WHEN count(*) OVER nxt = 4 THEN median(complaints) OVER nxt END AS after_median
  FROM g
  WINDOW prior AS (PARTITION BY company, product, issue ORDER BY week ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING),
         nxt AS (PARTITION BY company, product, issue ORDER BY week ROWS BETWEEN 1 FOLLOWING AND 4 FOLLOWING)
)
SELECT company, product, issue, week, complaints, repeats, baseline, after_median
FROM b
ORDER BY company, product, issue, week;
