-- FY2026 snapshot: how each month's complaints stand at the time of the snapshot.
SELECT
  strftime(date_received, '%Y-%m') AS month,
  count(*) AS complaints,
  count(*) FILTER (WHERE company_response = 'In progress') AS in_progress,
  count(*) FILTER (WHERE NOT timely_response) AS not_timely,
  count(*) FILTER (WHERE company_response = 'Untimely response') AS untimely_response,
  count(*) FILTER (WHERE company_response = 'Closed with monetary relief') AS monetary_relief,
  count(*) FILTER (WHERE company_response = 'Closed with non-monetary relief') AS non_monetary_relief
FROM complaints
GROUP BY month
ORDER BY month
