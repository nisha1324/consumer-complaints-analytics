-- Complaints per US federal fiscal year (October to September), full history (view: monthly).
-- FY2012 starts with the database in December 2011; the current fiscal year is partial.
SELECT
  CAST(left(month, 4) AS INTEGER) + CASE WHEN CAST(right(month, 2) AS INTEGER) >= 10 THEN 1 ELSE 0 END AS fiscal_year,
  min(month) AS first_month,
  max(month) AS last_month,
  sum(complaints) AS complaints,
  sum(complaints) FILTER (WHERE product IN ('Credit reporting or other personal consumer reports',
                                            'Credit reporting, credit repair services, or other personal consumer reports',
                                            'Credit reporting')) AS credit_reporting
FROM monthly
GROUP BY ALL
ORDER BY fiscal_year
