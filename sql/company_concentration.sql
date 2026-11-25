-- FY2026 snapshot: companies ranked by complaints, with the running share of all complaints.
-- Ties are broken by name so the ranking is fixed.
SELECT
  row_number() OVER (ORDER BY complaints DESC, company) AS rank,
  company,
  complaints,
  sum(complaints) OVER (ORDER BY complaints DESC, company) / sum(complaints) OVER () AS cumulative_share
FROM (SELECT company, count(*) AS complaints FROM complaints GROUP BY company)
ORDER BY rank
