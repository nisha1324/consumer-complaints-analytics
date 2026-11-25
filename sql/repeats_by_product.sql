-- FY2026 snapshot: complaints identical to an earlier complaint (lower ID) on every field
-- except the ID, by product. The data has no consumer identifier, so a repeat may be one
-- person filing several complaints (for example about several debts) or a duplicate filing.
WITH ranked AS (
  SELECT product,
         row_number() OVER (
           PARTITION BY date_received, date_sent_to_company, product, sub_product, issue, sub_issue,
                        company, state, zip_code, tags, submitted_via, company_response,
                        company_public_response, timely_response
           ORDER BY complaint_id) AS nth
  FROM complaints
)
SELECT product,
       count(*) AS complaints,
       count(*) FILTER (WHERE nth > 1) AS repeats,
       count(*) FILTER (WHERE nth > 1) / count(*) AS repeat_share
FROM ranked
GROUP BY product
ORDER BY repeats DESC, product
