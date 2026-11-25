-- Company names that become the same once case, spaces and punctuation are ignored are merged
-- under the spelling with the most complaints in the whole history (ties: alphabetical).
-- Part 1 found 4 such companies in the FY2026 snapshot; the whole history has 12.
CREATE OR REPLACE VIEW company_names AS
WITH n AS (
  SELECT company, regexp_replace(upper(company), '[^A-Z0-9]', '', 'g') AS name_key, sum(complaints) AS complaints
  FROM company_monthly
  GROUP BY company
)
SELECT company, name_key,
       first_value(company) OVER (PARTITION BY name_key ORDER BY complaints DESC, company) AS company_merged
FROM n;
