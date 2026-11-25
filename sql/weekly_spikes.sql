-- FY2026 snapshot: complaints per full week (Monday to Sunday, inside the window) and product,
-- flagged with the same rule as the monthly spikes but against the 8 weeks before and after:
-- at least {ratio} times the larger of the two medians and at least {min_excess} complaints above it.
WITH weeks AS (
  SELECT CAST(w AS DATE) AS week
  FROM range(DATE '{first_week}', DATE '{last_week}' + INTERVAL 1 DAY, INTERVAL 7 DAY) t(w)
), products AS (
  SELECT DISTINCT product FROM complaints
), counts AS (
  SELECT product, CAST(date_trunc('week', date_received) AS DATE) AS week, count(*) AS complaints
  FROM complaints GROUP BY ALL
), g AS (
  SELECT p.product, w.week, coalesce(c.complaints, 0) AS complaints
  FROM products p CROSS JOIN weeks w LEFT JOIN counts c ON c.product = p.product AND c.week = w.week
), s AS (
  SELECT *,
         CASE WHEN count(*) OVER prior = 8 THEN median(complaints) OVER prior END AS prior_median,
         CASE WHEN count(*) OVER nxt = 8 THEN median(complaints) OVER nxt END AS next_median
  FROM g
  WINDOW prior AS (PARTITION BY product ORDER BY week ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING),
         nxt AS (PARTITION BY product ORDER BY week ROWS BETWEEN 1 FOLLOWING AND 8 FOLLOWING)
)
SELECT product, week, complaints, prior_median, next_median,
       complaints >= {ratio} * greatest(prior_median, next_median)
         AND complaints - greatest(prior_median, next_median) >= {min_excess} AS spike
FROM s
WHERE prior_median IS NOT NULL AND next_median IS NOT NULL
ORDER BY product, week;
