-- Data-quality checks on the FY2026 snapshot (view: complaints).
-- One row per check: how many complaints it affects. A check is a fact
-- about the data, not a filter: nothing is removed here.
WITH base AS (SELECT * FROM complaints),
-- complaints identical to an earlier complaint (lower ID) on every field except the ID
repeats AS (
  SELECT count(*) - count(DISTINCT (date_received, date_sent_to_company, product, sub_product, issue,
         sub_issue, company, state, zip_code, tags, submitted_via, company_response,
         company_public_response, timely_response)) AS n
  FROM base
),
-- issues that have a sub-issue on at least one complaint
issues_with_sub AS (
  SELECT DISTINCT product, issue FROM base WHERE sub_issue IS NOT NULL
),
-- company names that collide with another name once case, spaces and punctuation are ignored
name_keys AS (
  SELECT company, regexp_replace(upper(company), '[^A-Z0-9]', '', 'g') AS k FROM (SELECT DISTINCT company FROM base)
),
colliding AS (
  SELECT company FROM name_keys WHERE k IN (SELECT k FROM name_keys GROUP BY k HAVING count(*) > 1)
)
SELECT * FROM (
  SELECT 1 AS check_id, 'Complaint ID is not unique' AS check_name,
         count(*) - count(DISTINCT complaint_id) AS complaints FROM base
  UNION ALL
  SELECT 2, 'Date received outside the window',
         count(*) FILTER (WHERE date_received NOT BETWEEN DATE '2025-10-01' AND DATE '2026-09-30') FROM base
  UNION ALL
  SELECT 3, 'Sent to the company before it was received',
         count(*) FILTER (WHERE date_sent_to_company < date_received) FROM base
  UNION ALL
  SELECT 4, 'Sent to the company more than 14 days after it was received',
         count(*) FILTER (WHERE date_sent_to_company - date_received > 14) FROM base
  UNION ALL
  SELECT 5, 'Timely response is not Yes or No',
         count(*) FILTER (WHERE timely_response IS NULL) FROM base
  UNION ALL
  SELECT 6, 'Company response still "In progress"',
         count(*) FILTER (WHERE company_response = 'In progress') FROM base
  UNION ALL
  SELECT 7, 'Not timely: "Untimely response" (no response in time)',
         count(*) FILTER (WHERE company_response = 'Untimely response') FROM base
  UNION ALL
  SELECT 8, 'Not timely: closed, but late',
         count(*) FILTER (WHERE NOT timely_response AND company_response LIKE 'Closed%') FROM base
  UNION ALL
  SELECT 9, '"Untimely response" marked as timely',
         count(*) FILTER (WHERE company_response = 'Untimely response' AND timely_response) FROM base
  UNION ALL
  SELECT 10, 'State missing',
         count(*) FILTER (WHERE state IS NULL) FROM base
  UNION ALL
  SELECT 11, 'State not a two-letter code',
         count(*) FILTER (WHERE state IS NOT NULL AND NOT regexp_full_match(state, '[A-Z]{2}')) FROM base
  UNION ALL
  SELECT 12, 'ZIP code published as 3 digits only (small area)',
         count(*) FILTER (WHERE regexp_full_match(zip_code, '[0-9]{3}XX')) FROM base
  UNION ALL
  SELECT 13, 'ZIP code withheld (XXXXX)',
         count(*) FILTER (WHERE zip_code = 'XXXXX') FROM base
  UNION ALL
  SELECT 14, 'ZIP code missing',
         count(*) FILTER (WHERE zip_code IS NULL) FROM base
  UNION ALL
  SELECT 15, 'ZIP code in any other format',
         count(*) FILTER (WHERE zip_code IS NOT NULL
                          AND NOT regexp_full_match(zip_code, '[0-9]{5}|[0-9]{3}XX|XXXXX')) FROM base
  UNION ALL
  SELECT 16, 'Sub-issue missing, issue never has one',
         count(*) FILTER (WHERE sub_issue IS NULL AND (product, issue) NOT IN (SELECT (product, issue) FROM issues_with_sub)) FROM base
  UNION ALL
  SELECT 17, 'Sub-issue missing, issue has one on other complaints',
         count(*) FILTER (WHERE sub_issue IS NULL AND (product, issue) IN (SELECT (product, issue) FROM issues_with_sub)) FROM base
  UNION ALL
  SELECT 18, 'Sub-product missing',
         count(*) FILTER (WHERE sub_product IS NULL) FROM base
  UNION ALL
  SELECT 19, 'Identical to an earlier complaint on every field except the ID',
         (SELECT n FROM repeats)
  UNION ALL
  SELECT 20, 'Company name collides with another once case and punctuation are ignored',
         count(*) FILTER (WHERE company IN (SELECT company FROM colliding)) FROM base
  UNION ALL
  SELECT 21, 'Tagged both Older American and Servicemember (one combined value)',
         count(*) FILTER (WHERE tags = 'Older American, Servicemember') FROM base
)
ORDER BY check_id
