-- Complaints per month and current product on a full month grid (a month with no complaints is 0),
-- with two baselines and the spike flag:
--   prior_median: median of the 12 months before (needs all 12)
--   next_median:  median of the 6 months after (needs all 6)
--   spike:  at least {ratio} times the larger baseline and at least {min_excess} complaints above it,
--           i.e. far above both what came before and what came after, so a one-off, not a new level
--   recent: fewer than 6 months after, but at least {ratio} times the prior median and {min_excess} above it
-- adjusted = the larger baseline in spike months, the count otherwise.
-- fiscal_year: US federal fiscal year (October to September).
CREATE OR REPLACE TABLE product_months AS
WITH counts AS (
  SELECT current_product, month, sum(complaints) AS complaints FROM history GROUP BY ALL
), bounds AS (
  SELECT current_product, min(month) AS first_month FROM counts GROUP BY ALL
), months AS (
  SELECT strftime(m, '%Y-%m') AS month
  FROM range(DATE '2011-12-01', DATE '{last_month}-01' + INTERVAL 1 MONTH, INTERVAL 1 MONTH) t(m)
), grid AS (
  SELECT b.current_product, m.month, coalesce(c.complaints, 0) AS complaints
  FROM bounds b
  JOIN months m ON m.month >= b.first_month
  LEFT JOIN counts c ON c.current_product = b.current_product AND c.month = m.month
), w AS (
  SELECT *,
         median(complaints) OVER prior AS prior_median_any, count(*) OVER prior AS prior_months,
         median(complaints) OVER nxt AS next_median_any, count(*) OVER nxt AS next_months
  FROM grid
  WINDOW prior AS (PARTITION BY current_product ORDER BY month ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING),
         nxt AS (PARTITION BY current_product ORDER BY month ROWS BETWEEN 1 FOLLOWING AND 6 FOLLOWING)
), b AS (
  SELECT current_product, month, complaints,
         CASE WHEN prior_months = 12 THEN prior_median_any END AS prior_median,
         CASE WHEN next_months = 6 THEN next_median_any END AS next_median
  FROM w
), f AS (
  SELECT *,
         CASE WHEN prior_median IS NOT NULL AND next_median IS NOT NULL
              THEN greatest(prior_median, next_median) END AS baseline
  FROM b
)
SELECT current_product, month,
       CAST(left(month, 4) AS INTEGER) + CASE WHEN CAST(right(month, 2) AS INTEGER) >= 10 THEN 1 ELSE 0 END
         AS fiscal_year,
       complaints, prior_median, next_median, baseline,
       CASE
         WHEN baseline IS NOT NULL AND complaints >= {ratio} * baseline AND complaints - baseline >= {min_excess}
           THEN 'spike'
         WHEN baseline IS NULL AND next_median IS NULL AND prior_median IS NOT NULL
              AND complaints >= {ratio} * prior_median AND complaints - prior_median >= {min_excess}
           THEN 'recent'
       END AS status
FROM f
ORDER BY current_product, month;
