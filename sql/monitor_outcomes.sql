-- Part 4, outcome monitor: for each company, the share of final responses with an outcome
-- ({metric}: relief or late, from sql/responses.sql) in the latest {recent} full weeks, against the
-- {before} weeks before them, by week received. Companies with {min_responses}+ final responses in
-- the window; every week on a full grid (a week with none adds 0).
--   recent_n / recent_k:  final responses / with the outcome, this week and the {recent_minus_1} before
--   before_n / before_k:  the same for the {before} weeks before those (needs all of them)
WITH weeks AS (
  SELECT CAST(w AS DATE) AS week
  FROM range(DATE '{first_week}', DATE '{last_week}' + INTERVAL 1 DAY, INTERVAL 7 DAY) t(w)
), r AS (
  SELECT * FROM responses
  WHERE date_received >= DATE '{first_week}' AND date_received < DATE '{last_week}' + INTERVAL 7 DAY
), c AS (
  SELECT company_merged AS company, CAST(date_trunc('week', date_received) AS DATE) AS week,
         count(*) AS n, sum({metric}) AS k
  FROM r GROUP BY ALL
), companies AS (
  SELECT company_merged AS company FROM r GROUP BY ALL HAVING count(*) >= {min_responses}
), g AS (
  SELECT co.company, w.week, coalesce(c.n, 0) AS n, coalesce(c.k, 0) AS k
  FROM companies co CROSS JOIN weeks w LEFT JOIN c ON c.company = co.company AND c.week = w.week
)
SELECT company, week, n, k,
       sum(n) OVER recent AS recent_n, sum(k) OVER recent AS recent_k,
       CASE WHEN count(*) OVER before = {before} THEN sum(n) OVER before END AS before_n,
       CASE WHEN count(*) OVER before = {before} THEN sum(k) OVER before END AS before_k
FROM g
WINDOW recent AS (PARTITION BY company ORDER BY week ROWS BETWEEN {recent_minus_1} PRECEDING AND CURRENT ROW),
       before AS (PARTITION BY company ORDER BY week ROWS BETWEEN {before_end} PRECEDING AND {recent} PRECEDING)
ORDER BY company, week;
