-- Part 3: how complaints end, by product (final responses; in-progress counted separately).
SELECT
  c.product,
  count(*) AS complaints,
  count(*) FILTER (WHERE c.company_response = 'In progress') AS in_progress,
  count(*) FILTER (WHERE c.company_response <> 'In progress') AS final_responses,
  count(*) FILTER (WHERE c.company_response = 'Closed with monetary relief') AS monetary_relief,
  count(*) FILTER (WHERE c.company_response = 'Closed with non-monetary relief') AS non_monetary_relief,
  count(*) FILTER (WHERE c.company_response = 'Closed with explanation') AS explanation,
  count(*) FILTER (WHERE c.company_response = 'Untimely response') AS untimely_response,
  count(*) FILTER (WHERE c.company_response <> 'Untimely response' AND c.company_response <> 'In progress'
                   AND NOT c.timely_response) AS closed_late,
  count(DISTINCT c.company_merged) FILTER (WHERE c.company_response <> 'In progress') AS companies
FROM complaints_flagged c
GROUP BY c.product
ORDER BY complaints DESC, c.product;
