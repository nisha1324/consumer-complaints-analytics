-- FY2026 snapshot: complaints by product and issue, with and without the repeats, and each issue's
-- share of its product.
WITH c AS (
  SELECT product, issue,
         count(*) AS complaints,
         count(*) FILTER (WHERE NOT is_repeat) AS complaints_no_repeats
  FROM complaints_flagged
  GROUP BY ALL
)
SELECT product, issue, complaints,
       complaints / sum(complaints) OVER (PARTITION BY product) AS share,
       complaints_no_repeats,
       complaints_no_repeats / sum(complaints_no_repeats) OVER (PARTITION BY product) AS share_no_repeats
FROM c
ORDER BY product, complaints DESC, issue;
