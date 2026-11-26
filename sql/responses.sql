-- Part 3: final responses only (complaints still "In progress" have no outcome yet).
-- Built on complaints_flagged (merged company names, repeat flag).
--   relief:    closed with monetary or non-monetary relief
--   monetary:  closed with monetary relief
--   late:      not timely in either form: "Untimely response" (the company did not respond in
--              time and has no outcome) or a closing response flagged timely = No
-- An untimely response counts as a final response with no relief.
CREATE OR REPLACE VIEW responses AS
SELECT *,
       CAST(company_response IN ('Closed with monetary relief', 'Closed with non-monetary relief') AS INTEGER) AS relief,
       CAST(company_response = 'Closed with monetary relief' AS INTEGER) AS monetary,
       CAST(company_response = 'Untimely response' OR NOT timely_response AS INTEGER) AS late,
       date_received < DATE '2026-04-01' AS first_half
FROM complaints_flagged
WHERE company_response <> 'In progress';
