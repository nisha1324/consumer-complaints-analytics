-- Part 3: relief by company in the first half of FY2026 (October to March) and the second
-- (April to September), to find companies whose relief rate changed during the year.
SELECT company_merged AS company,
       count(*) FILTER (WHERE first_half) AS n1,
       sum(relief) FILTER (WHERE first_half) AS relief1,
       count(*) FILTER (WHERE NOT first_half) AS n2,
       sum(relief) FILTER (WHERE NOT first_half) AS relief2
FROM responses
GROUP BY company_merged
ORDER BY company;
