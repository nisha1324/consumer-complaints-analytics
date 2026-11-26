-- Part 3: relief rate by month as observed, and as expected from the month's product x issue mix
-- at the full-year rate of each cell. {where} can leave companies out (e.g. one that changed its
-- practice); the full-year cell rates are then computed without them too.
WITH r AS (SELECT * FROM responses WHERE {where}),
cells AS (SELECT product, issue, avg(relief) AS p FROM r GROUP BY ALL)
SELECT strftime(r.date_received, '%Y-%m') AS month,
       count(*) AS final_responses,
       sum(r.relief) AS relief,
       avg(r.relief) AS relief_rate,
       avg(cells.p) AS expected_rate
FROM r JOIN cells USING (product, issue)
GROUP BY month
ORDER BY month;
