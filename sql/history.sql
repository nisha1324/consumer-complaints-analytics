-- The full history under current product names and merged company names
-- (product_map is registered from complaints/taxonomy.py).
CREATE OR REPLACE VIEW history AS
SELECT h.month, m.current_product, c.company_merged AS company, sum(h.complaints) AS complaints
FROM company_monthly h
JOIN product_map m ON h.product = m.product AND h.sub_product IS NOT DISTINCT FROM m.sub_product
JOIN company_names c ON h.company = c.company
GROUP BY ALL;
