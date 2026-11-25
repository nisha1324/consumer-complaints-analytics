-- One row per column of the snapshot: filled, distinct values, most common value.
-- {col} is replaced by each column name in turn (complaints/profile.py).
SELECT
  '{col}' AS column_name,
  count(*) AS complaints,
  count({col}) AS filled,
  count(DISTINCT {col}) AS distinct_values,
  (SELECT CAST({col} AS VARCHAR) FROM complaints WHERE {col} IS NOT NULL
   GROUP BY {col} ORDER BY count(*) DESC, CAST({col} AS VARCHAR) LIMIT 1) AS most_common,
  (SELECT count(*) FROM complaints WHERE {col} IS NOT NULL
   GROUP BY {col} ORDER BY count(*) DESC, CAST({col} AS VARCHAR) LIMIT 1) AS most_common_complaints
FROM complaints
