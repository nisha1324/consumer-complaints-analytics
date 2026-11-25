-- FY2025 -> FY2026 change by company, per current product, as average complaints per month over the
-- months that are not spikes for that product (so a one-off month in either year does not drive it).
-- Company changes add up exactly to the product's change.
WITH m AS (
  SELECT current_product, month, fiscal_year FROM product_months
  WHERE fiscal_year IN (2025, 2026) AND status IS DISTINCT FROM 'spike'
), months AS (
  SELECT current_product,
         count(*) FILTER (WHERE fiscal_year = 2025) AS months_2025,
         count(*) FILTER (WHERE fiscal_year = 2026) AS months_2026
  FROM m GROUP BY ALL
), c AS (
  SELECT h.current_product, h.company,
         coalesce(sum(h.complaints) FILTER (WHERE m.fiscal_year = 2025), 0) AS complaints_2025,
         coalesce(sum(h.complaints) FILTER (WHERE m.fiscal_year = 2026), 0) AS complaints_2026
  FROM history h JOIN m ON h.current_product = m.current_product AND h.month = m.month
  GROUP BY ALL
)
SELECT c.current_product, c.company, months_2025, months_2026, complaints_2025, complaints_2026,
       complaints_2025 / months_2025 AS per_month_2025,
       complaints_2026 / months_2026 AS per_month_2026,
       complaints_2026 / months_2026 - complaints_2025 / months_2025 AS change_per_month
FROM c JOIN months USING (current_product)
ORDER BY c.current_product, change_per_month DESC, c.company;
