-- Part 3: each company's observed and expected count of {metric} (relief or monetary), allowing
-- for its product x issue mix (indirect standardisation).
--   * peer rate of a cell = the rate of every OTHER company in the same product and issue
--     (the company itself is left out, so a large company is compared with its peers, not itself);
--   * if the peers have fewer than {min_peer} final responses in that cell, the peer rate of the
--     whole product is used instead (again without the company), then that of all products;
--   * expected = sum over the company's complaints of the peer rate; variance = sum of p(1 - p),
--     the spread chance alone would give if the company handled complaints like its peers.
-- {where} narrows the responses (e.g. "NOT is_repeat"); "TRUE" keeps them all.
WITH r AS (SELECT * FROM responses WHERE {where}),
cell AS (
  SELECT company_merged AS company, product, issue, count(*) AS n, sum({metric}) AS o
  FROM r GROUP BY ALL
),
cell_all AS (SELECT product, issue, sum(n) AS n, sum(o) AS o FROM cell GROUP BY ALL),
prod_all AS (SELECT product, sum(n) AS n, sum(o) AS o FROM cell GROUP BY ALL),
prod_co AS (SELECT company, product, sum(n) AS n, sum(o) AS o FROM cell GROUP BY ALL),
all_all AS (SELECT sum(n) AS n, sum(o) AS o FROM cell),
co_all AS (SELECT company, sum(n) AS n, sum(o) AS o FROM cell GROUP BY ALL),
peer AS (
  SELECT cell.company, cell.product, cell.issue, cell.n, cell.o,
         CASE WHEN ca.n - cell.n >= {min_peer} THEN (ca.o - cell.o) / (ca.n - cell.n)
              WHEN pa.n - pc.n > 0 THEN (pa.o - pc.o) / (pa.n - pc.n)
              ELSE (aa.o - co.o) / (aa.n - co.n) END AS p,
         CASE WHEN ca.n - cell.n >= {min_peer} THEN 'product x issue'
              WHEN pa.n - pc.n > 0 THEN 'product' ELSE 'all' END AS level
  FROM cell
  JOIN cell_all ca USING (product, issue)
  JOIN prod_all pa USING (product)
  JOIN prod_co pc ON pc.company = cell.company AND pc.product = cell.product
  JOIN co_all co ON co.company = cell.company
  CROSS JOIN all_all aa
)
SELECT company,
       sum(n) AS final_responses,
       sum(o) AS observed,
       sum(n * p) AS expected,
       sum(n * p * (1 - p)) AS variance,
       sum(n) FILTER (WHERE level <> 'product x issue') AS fallback_responses,
       count(DISTINCT product) AS products,
       arg_max(product, n) AS main_product
FROM peer
GROUP BY company
ORDER BY final_responses DESC, company;
