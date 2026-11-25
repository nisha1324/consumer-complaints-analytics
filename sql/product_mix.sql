-- FY2026 snapshot: complaints, companies and share by product.
SELECT
  product,
  count(*) AS complaints,
  count(DISTINCT company) AS companies,
  count(*) / sum(count(*)) OVER () AS share
FROM complaints
GROUP BY product
ORDER BY complaints DESC, product
