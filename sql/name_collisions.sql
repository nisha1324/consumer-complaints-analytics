-- FY2026 snapshot: company names that become the same once case, spaces and punctuation
-- are ignored (likely the same company spelled two ways).
WITH names AS (
  SELECT company, regexp_replace(upper(company), '[^A-Z0-9]', '', 'g') AS name_key, count(*) AS complaints
  FROM complaints
  GROUP BY company
)
SELECT name_key, company, complaints
FROM names
WHERE name_key IN (SELECT name_key FROM names GROUP BY name_key HAVING count(*) > 1)
ORDER BY name_key, complaints DESC, company
