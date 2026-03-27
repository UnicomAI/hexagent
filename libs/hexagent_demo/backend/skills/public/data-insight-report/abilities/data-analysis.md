# Data Analysis Ability

You are an expert data analyst with expertise in SQL, Python (pandas), and statistical analysis.

## When to Apply

Use this ability when:
- Writing SQL queries for data extraction
- Analyzing datasets with pandas
- Performing statistical analysis
- Creating data transformations
- Identifying data patterns and insights
- Data cleaning and preparation

## Core Competencies

### SQL Analysis (via Script)
- Schema inspection and data profiling
- Complex queries with JOINs, subqueries, CTEs
- Window functions and aggregations
- Statistical summaries
- Result export to CSV/JSON/Markdown

### pandas Analysis (via Code)
- Data manipulation and transformation
- Grouping, filtering, pivoting
- Time series analysis
- Handling missing data
- Custom statistical analysis
- Data visualization preparation

### Statistics
- Descriptive statistics
- Hypothesis testing
- Correlation analysis
- Trend analysis
- Outlier detection

---

## Supported Data Formats

| Format | Extensions | Description |
|--------|------------|-------------|
| Excel | `.xlsx`, `.xls`, `.xlsm` | Microsoft Excel workbooks |
| CSV | `.csv` | Comma-separated values |
| TSV | `.tsv`, `.tab` | Tab-separated values |
| JSON | `.json` | JSON files |
| Parquet | `.parquet` | Apache Parquet files |

---

## Method 1: SQL Analysis (Script-Based)

Use `scripts/analyze.py` for quick SQL-based analysis with DuckDB.

### Script Location

```
scripts/analyze.py
```

### Actions

| Action | Description |
|--------|-------------|
| `inspect` | View schema, columns, types, sample data |
| `query` | Execute SQL queries |
| `summary` | Generate statistical summaries |

### Usage Examples

#### Inspect File Structure

```bash
python scripts/analyze.py \
  --files /path/to/data.xlsx \
  --action inspect
```

Returns: sheet names, columns, data types, row counts, sample data.

#### Execute SQL Query

```bash
python scripts/analyze.py \
  --files /path/to/data.xlsx \
  --action query \
  --sql "SELECT category, COUNT(*) as count, AVG(amount) as avg_amount FROM Sheet1 GROUP BY category ORDER BY count DESC"
```

#### Generate Statistical Summary

```bash
python scripts/analyze.py \
  --files /path/to/data.xlsx \
  --action summary \
  --table Sheet1
```

#### Export Results

```bash
python scripts/analyze.py \
  --files /path/to/data.xlsx \
  --action query \
  --sql "SELECT * FROM Sheet1 WHERE amount > 1000" \
  --output-file /path/to/output/results.csv
```

### SQL Analysis Patterns

#### Basic Exploration

```sql
-- Row count
SELECT COUNT(*) FROM Sheet1

-- Distinct values
SELECT DISTINCT category FROM Sheet1

-- Value distribution
SELECT category, COUNT(*) as cnt
FROM Sheet1
GROUP BY category
ORDER BY cnt DESC

-- Date range
SELECT MIN(date_col), MAX(date_col) FROM Sheet1
```

#### Aggregation & Grouping

```sql
-- Revenue by category and month
SELECT category,
       DATE_TRUNC('month', order_date) as month,
       SUM(revenue) as total_revenue
FROM Sales
GROUP BY category, month
ORDER BY month, total_revenue DESC

-- Top 10 customers
SELECT customer_name, SUM(amount) as total_spend
FROM Orders
GROUP BY customer_name
ORDER BY total_spend DESC
LIMIT 10
```

#### Window Functions

```sql
-- Running total and rank
SELECT order_date, amount,
       SUM(amount) OVER (ORDER BY order_date) as running_total,
       RANK() OVER (ORDER BY amount DESC) as amount_rank
FROM Sales
```

---

## Method 2: pandas Analysis (Code-Based)

Use pandas for flexible, programmatic data analysis with Python code.

### When to Use pandas vs SQL

| Use pandas when... | Use SQL when... |
|-------------------|-----------------|
| Need complex data transformations | Quick aggregations and filtering |
| Custom statistical analysis | Standard summaries |
| Data cleaning with conditional logic | Simple joins and grouping |
| Time series manipulation | Large datasets (DuckDB is faster) |
| Iterative exploration | One-time queries |
| Need to chain multiple operations | Export to file directly |

### Loading Data

```python
import pandas as pd

# Excel
df = pd.read_excel('data.xlsx', sheet_name='Sheet1')
df = pd.read_excel('data.xlsx', sheet_name=None)  # All sheets as dict

# CSV
df = pd.read_csv('data.csv')
df = pd.read_csv('data.csv', encoding='utf-8', parse_dates=['date_col'])

# TSV
df = pd.read_csv('data.tsv', sep='\t')

# JSON
df = pd.read_json('data.json')
```

### Data Inspection

```python
# Basic info
df.info()
df.shape
df.columns.tolist()
df.dtypes

# Preview
df.head(10)
df.tail(5)
df.sample(5)

# Statistical summary
df.describe()
df.describe(include='all')

# Missing values
df.isnull().sum()
df.isnull().mean() * 100  # Percentage

# Unique values
df['column'].nunique()
df['column'].value_counts()
```

### Data Cleaning

```python
# Handle missing values
df.dropna()                          # Drop rows with any missing
df.dropna(subset=['col1', 'col2'])   # Drop if specific columns missing
df.fillna(0)                         # Fill with value
df.fillna({'col1': 0, 'col2': 'unknown'})  # Fill per column
df['col'].fillna(df['col'].mean())   # Fill with mean

# Remove duplicates
df.drop_duplicates()
df.drop_duplicates(subset=['id'])
df.duplicated().sum()  # Count duplicates

# Type conversion
df['date'] = pd.to_datetime(df['date'])
df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
df['category'] = df['category'].astype('category')

# String cleaning
df['name'] = df['name'].str.strip()
df['name'] = df['name'].str.lower()
df['name'] = df['name'].str.replace(r'\s+', ' ', regex=True)

# Outlier handling
q1 = df['amount'].quantile(0.25)
q3 = df['amount'].quantile(0.75)
iqr = q3 - q1
df_clean = df[(df['amount'] >= q1 - 1.5*iqr) & (df['amount'] <= q3 + 1.5*iqr)]
```

### Data Transformation

```python
# Filtering
df[df['amount'] > 100]
df[(df['amount'] > 100) & (df['category'] == 'A')]
df.query('amount > 100 and category == "A"')
df[~df['category'].isin(['A', 'B'])]  # Exclude

# Sorting
df.sort_values('amount', ascending=False)
df.sort_values(['category', 'amount'], ascending=[True, False])

# Column operations
df['new_col'] = df['col1'] + df['col2']
df['ratio'] = df['amount'] / df['total']
df['log_amount'] = np.log(df['amount'])

# Rename columns
df.rename(columns={'old_name': 'new_name'})
df.columns = ['col1', 'col2', 'col3']  # All at once

# Select/reorder columns
df[['col1', 'col2', 'col3']]
df.drop(columns=['col1', 'col2'])
```

### Grouping & Aggregation

```python
# Basic groupby
df.groupby('category')['amount'].sum()
df.groupby('category')['amount'].agg(['sum', 'mean', 'count'])

# Multiple columns
df.groupby(['category', 'region'])['amount'].sum()

# Multiple aggregations
df.groupby('category').agg({
    'amount': ['sum', 'mean', 'std'],
    'quantity': ['sum', 'count'],
    'date': ['min', 'max']
})

# Custom aggregations
df.groupby('category')['amount'].agg(
    total='sum',
    average='mean',
    count='count',
    range_=lambda x: x.max() - x.min()
)

# Transform (preserve shape)
df['category_avg'] = df.groupby('category')['amount'].transform('mean')

# Filter groups
df.groupby('category').filter(lambda x: x['amount'].sum() > 1000)
```

### Pivot Tables & Cross-tabs

```python
# Pivot table
df.pivot_table(
    values='amount',
    index='category',
    columns='region',
    aggfunc='sum',
    fill_value=0
)

# Multiple aggregations
df.pivot_table(
    values='amount',
    index='category',
    columns='region',
    aggfunc=['sum', 'mean', 'count']
)

# Cross-tabulation
pd.crosstab(df['category'], df['region'])
pd.crosstab(df['category'], df['region'], normalize='index')  # Row percentages
```

### Time Series Analysis

```python
# Convert to datetime
df['date'] = pd.to_datetime(df['date'])

# Set datetime index
df = df.set_index('date')

# Resample (time-based grouping)
df.resample('M')['amount'].sum()      # Monthly
df.resample('W')['amount'].mean()     # Weekly
df.resample('Q')['amount'].sum()      # Quarterly

# Rolling windows
df['rolling_avg'] = df['amount'].rolling(window=7).mean()
df['rolling_sum'] = df['amount'].rolling(window=30).sum()

# Date components
df['year'] = df['date'].dt.year
df['month'] = df['date'].dt.month
df['day'] = df['date'].dt.day
df['weekday'] = df['date'].dt.day_name()
df['quarter'] = df['date'].dt.quarter

# Shift (lag/lead)
df['prev_amount'] = df['amount'].shift(1)
df['pct_change'] = df['amount'].pct_change()
```

### Statistical Analysis

```python
import numpy as np
from scipy import stats

# Descriptive statistics
df['amount'].describe()
df['amount'].mean()
df['amount'].median()
df['amount'].std()
df['amount'].var()
df['amount'].quantile([0.25, 0.5, 0.75])

# Correlation
df.corr()  # Correlation matrix
df.corr()['target']  # Correlation with target
df[['col1', 'col2', 'col3']].corr()

# Covariance
df.cov()

# Hypothesis testing
stats.ttest_ind(df[df['group'] == 'A']['amount'],
                df[df['group'] == 'B']['amount'])

stats.chi2_contingency(pd.crosstab(df['cat1'], df['cat2']))

# Normality test
stats.normaltest(df['amount'])

# Correlation test
stats.pearsonr(df['col1'], df['col2'])
stats.spearmanr(df['col1'], df['col2'])
```

### Data Merging

```python
# Concatenate
pd.concat([df1, df2], axis=0)  # Stack vertically
pd.concat([df1, df2], axis=1)  # Side by side

# Merge (SQL-style joins)
pd.merge(df1, df2, on='key')                    # Inner join
pd.merge(df1, df2, on='key', how='left')        # Left join
pd.merge(df1, df2, on='key', how='right')       # Right join
pd.merge(df1, df2, on='key', how='outer')       # Full outer join

# Merge on different column names
pd.merge(df1, df2, left_on='id', right_on='customer_id')

# Join on index
df1.join(df2, on='key')
```

### Exporting Data

```python
# To CSV
df.to_csv('output.csv', index=False)
df.to_csv('output.csv', index=False, encoding='utf-8-sig')

# To Excel
df.to_excel('output.xlsx', index=False, sheet_name='Sheet1')

# To JSON
df.to_json('output.json', orient='records', indent=2)

# To Markdown table
print(df.to_markdown(index=False))

# To HTML
df.to_html('output.html', index=False)
```

---

## Method 3: Statistical Analysis Examples

### Correlation Analysis

```python
import pandas as pd
import numpy as np

# Load data
df = pd.read_excel('data.xlsx')

# Correlation matrix
corr_matrix = df.select_dtypes(include=[np.number]).corr()

# Find highly correlated pairs
high_corr = []
for i in range(len(corr_matrix.columns)):
    for j in range(i+1, len(corr_matrix.columns)):
        if abs(corr_matrix.iloc[i, j]) > 0.7:
            high_corr.append({
                'var1': corr_matrix.columns[i],
                'var2': corr_matrix.columns[j],
                'correlation': corr_matrix.iloc[i, j]
            })

high_corr_df = pd.DataFrame(high_corr)
print(high_corr_df)
```

### Trend Analysis

```python
import pandas as pd
from scipy import stats

df = pd.read_excel('sales.xlsx')
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date')

# Monthly trend
monthly = df.resample('M', on='date')['amount'].sum().reset_index()

# Linear regression for trend
x = np.arange(len(monthly))
y = monthly['amount'].values
slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

print(f"Trend slope: {slope:.2f} per month")
print(f"R-squared: {r_value**2:.3f}")
print(f"P-value: {p_value:.4f}")

# Trend direction
if slope > 0 and p_value < 0.05:
    print("Significant upward trend")
elif slope < 0 and p_value < 0.05:
    print("Significant downward trend")
else:
    print("No significant trend")
```

### Outlier Detection

```python
import pandas as pd
import numpy as np

df = pd.read_excel('data.xlsx')

# IQR method
def detect_outliers_iqr(series, multiplier=1.5):
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    return (series < lower) | (series > upper)

# Z-score method
def detect_outliers_zscore(series, threshold=3):
    z_scores = np.abs((series - series.mean()) / series.std())
    return z_scores > threshold

# Apply
for col in df.select_dtypes(include=[np.number]).columns:
    outliers_iqr = detect_outliers_iqr(df[col])
    outliers_zscore = detect_outliers_zscore(df[col])
    print(f"{col}: {outliers_iqr.sum()} outliers (IQR), {outliers_zscore.sum()} outliers (Z-score)")
```

### Segmentation Analysis

```python
import pandas as pd

df = pd.read_excel('customers.xlsx')

# RFM-like segmentation
df['recency_score'] = pd.qcut(df['days_since_last_purchase'], 5, labels=[5,4,3,2,1])
df['frequency_score'] = pd.qcut(df['purchase_count'].rank(method='first'), 5, labels=[1,2,3,4,5])
df['monetary_score'] = pd.qcut(df['total_spent'].rank(method='first'), 5, labels=[1,2,3,4,5])

df['rfm_score'] = df['recency_score'].astype(str) + df['frequency_score'].astype(str) + df['monetary_score'].astype(str)

# Segment summary
segments = df.groupby('rfm_score').agg({
    'customer_id': 'count',
    'total_spent': ['mean', 'sum'],
    'purchase_count': 'mean'
}).round(2)

print(segments)
```

---

## Analysis Workflow Recommendation

### For Quick Analysis (Use SQL Script)

1. **Inspect**: `python scripts/analyze.py --files data.xlsx --action inspect`
2. **Summary**: `python scripts/analyze.py --files data.xlsx --action summary --table Sheet1`
3. **Query**: Write SQL for aggregations and filtering
4. **Export**: Use `--output-file` for results

### For Complex Analysis (Use pandas)

1. **Load**: `pd.read_excel()` or `pd.read_csv()`
2. **Clean**: Handle missing values, duplicates, type conversions
3. **Explore**: `describe()`, `info()`, `value_counts()`
4. **Transform**: Group, pivot, merge, calculate new columns
5. **Analyze**: Statistical tests, correlation, trends
6. **Export**: `to_csv()`, `to_excel()`, `to_markdown()`

### When to Combine Both

```
1. Use SQL script for initial inspection and quick queries
2. Export subset of data for deeper pandas analysis
3. Use pandas for custom transformations and statistics
4. Use SQL for final aggregations if working with large data
```

---

## Parameters Reference

### SQL Script Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--files` | Yes | Space-separated paths to data files |
| `--action` | Yes | One of: `inspect`, `query`, `summary` |
| `--sql` | For `query` | SQL query to execute |
| `--table` | For `summary` | Table/sheet name to summarize |
| `--output-file` | No | Path to export results (CSV/JSON/MD) |

### Common pandas Parameters

```python
# read_excel
pd.read_excel(file, sheet_name=0, header=0, usecols=None, dtype=None, parse_dates=None)

# read_csv
pd.read_csv(file, sep=',', header=0, encoding=None, parse_dates=None, chunksize=None)

# to_csv
df.to_csv(file, index=True, encoding='utf-8', sep=',')

# to_excel
df.to_excel(file, sheet_name='Sheet1', index=True)
```

---

## Notes

- DuckDB (SQL script) is faster for large datasets (100MB+)
- pandas is more flexible for complex transformations
- Use SQL for joins and simple aggregations
- Use pandas for custom logic and iterative analysis
- Cache is automatic for SQL script — repeated queries are instant

---

## Integration with Data Insight Report

When using this ability within the `data-insight-report` skill:

1. Use SQL script for initial data profiling (`inspect`, `summary`)
2. Use pandas for complex transformations and statistical analysis
3. Export processed data to CSV for chart generation
4. Document findings for insight planning phase

The analysis results feed directly into:
- Data quality assessment
- Insight planning
- Chart data preparation
- Statistical insights for the report
