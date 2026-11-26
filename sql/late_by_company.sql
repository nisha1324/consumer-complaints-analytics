-- Part 3: late responses by company, both forms counted (final responses only).
SELECT company_merged AS company,
       count(*) AS final_responses,
       sum(late) AS late,
       count(*) FILTER (WHERE company_response = 'Untimely response') AS untimely_response,
       sum(late) - count(*) FILTER (WHERE company_response = 'Untimely response') AS closed_late,
       arg_max(product, n_product) AS main_product
FROM (SELECT *, count(*) OVER (PARTITION BY company_merged, product) AS n_product FROM responses)
GROUP BY company_merged
ORDER BY late DESC, company;
