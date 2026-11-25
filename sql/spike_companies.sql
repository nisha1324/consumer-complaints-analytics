-- For each spike month: every company's complaints that month against its own average month over
-- the 12 months before (months with no complaints count as 0). The company excesses add up exactly
-- to the product's excess over its own 12-month average.
WITH spikes AS (
  SELECT current_product, month, strftime(strptime(month, '%Y-%m') - INTERVAL 12 MONTH, '%Y-%m') AS from_month
  FROM product_months WHERE status = 'spike'
), x AS (
  SELECT s.current_product, s.month, h.company,
         coalesce(sum(h.complaints) FILTER (WHERE h.month = s.month), 0) AS complaints,
         coalesce(sum(h.complaints) FILTER (WHERE h.month < s.month), 0) / 12.0 AS prior_average
  FROM spikes s
  JOIN history h ON h.current_product = s.current_product AND h.month >= s.from_month AND h.month <= s.month
  GROUP BY ALL
)
SELECT current_product, month, company, complaints, prior_average, complaints - prior_average AS excess
FROM x
ORDER BY current_product, month, excess DESC, company;
