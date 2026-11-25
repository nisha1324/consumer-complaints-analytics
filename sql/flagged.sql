-- The FY2026 snapshot with merged company names and the repeat flag from Part 1: a repeat is
-- identical to an earlier complaint (lower ID) on every field except the ID.
CREATE OR REPLACE VIEW complaints_flagged AS
SELECT c.*, n.company_merged,
       row_number() OVER (
         PARTITION BY date_received, date_sent_to_company, product, sub_product, issue, sub_issue,
                      c.company, state, zip_code, tags, submitted_via, company_response,
                      company_public_response, timely_response
         ORDER BY complaint_id) > 1 AS is_repeat
FROM complaints c JOIN company_names n ON c.company = n.company;
