---
name: data-insight-report
description: |
  Analyze tabular data (Excel, CSV, TSV, etc.) and generate insightful ECharts visualizations embedded in comprehensive data insight reports.
  Use when: analyzing spreadsheet data for insights, creating data visualization dashboards, generating interactive chart reports,
  building presentation-ready data insight reports, or when user needs to transform tabular data into actionable insights with visualizations.
license: MIT
metadata:
  author: Andy Huang
  version: "1.3.0"
---

# Data Insight Report Generator

Expert **Data Analyst & Visualization Specialist** that analyzes tabular data (Excel, CSV, TSV, etc.) and generates comprehensive data insight reports with interactive ECharts visualizations and actionable recommendations.

## When to Use

- Analyzing Excel/CSV/TSV data for business insights
- Creating data visualization dashboards from spreadsheets
- Generating interactive chart reports for stakeholders
- Exploring and presenting data insights visually
- Building presentation-ready data insight reports with embedded charts
- Transforming raw tabular data into actionable business recommendations

## Supported Data Formats

| Format | Extensions | Description |
|--------|------------|-------------|
| Excel | `.xlsx`, `.xlsm`, `.xls` | Microsoft Excel workbooks |
| CSV | `.csv` | Comma-separated values |
| TSV | `.tsv`, `.tab` | Tab-separated values |
| Other | `.ods` | OpenDocument Spreadsheet |

---

## Capability Assessment - Access to Dedicated Documents

Based on the decomposed requirements, explicitly determine whether it is necessary to read the following specialized capability documents:

| Capability | When to Read | Document Path |
|------------|--------------|---------------|
| **data-analysis** | When performing ANY data analysis: SQL queries, pandas operations, statistics, data cleaning, transformations, pivot tables, time series, or data exploration | **Must** read `abilities/data-analysis.md` |
| **echarts-validation** | When validating ECharts chart configurations after generation, fixing chart errors, or understanding validation rules | **Must** read `abilities/echarts-validation.md` |

### Decision Flow

```
User Request
    │
    ├─► Need to load/inspect data files? ──► Read abilities/data-analysis.md
    │
    ├─► Need SQL queries or pandas analysis? ──► Read abilities/data-analysis.md
    │
    ├─► Need statistical summaries or correlations? ──► Read abilities/data-analysis.md
    │
    ├─► Need data cleaning or transformations? ──► Read abilities/data-analysis.md
    │
    ├─► Need to validate chart config? ──► Read abilities/echarts-validation.md
    │
    └─► Only need chart templates/report format? ──► Continue with current document
```

---

## Directory Structure

```
data-insight-report/
├── SKILL.md                       # Main skill document (this file)
├── abilities/
│   ├── data-analysis.md           # Data analysis capability (SQL + pandas + statistics)
│   └── echarts-validation.md      # ECharts validation capability
└── scripts/
    ├── analyze.py                 # SQL-based data analysis script (DuckDB)
    └── validate_echarts.py        # ECharts configuration validator
```

---

## Core Capabilities

### 1. Data Analysis (via data-analysis ability)

**Two complementary analysis methods:**

#### SQL Analysis (Script-Based)
- Quick data inspection via `scripts/analyze.py`
- Schema inspection, data profiling, statistical summaries
- Complex queries with JOINs, CTEs, window functions
- Export to CSV/JSON/Markdown

#### pandas Analysis (Code-Based)
- Flexible, programmatic data manipulation
- Advanced data cleaning and transformations
- Time series analysis
- Statistical analysis (correlations, hypothesis testing, trends)
- Custom data processing pipelines

**When to use which:**

| Use SQL Script when... | Use pandas when... |
|----------------------|-------------------|
| Quick data inspection | Complex transformations |
| Simple aggregations | Custom statistical analysis |
| Large datasets (>100MB) | Iterative exploration |
| One-time queries | Chained operations |
| Direct file export | Conditional logic |

**To use this capability, read `abilities/data-analysis.md` for detailed instructions.**

### 2. ECharts Validation (via echarts-validation ability)

- Automated JSON syntax validation
- ECharts structure validation (required fields, chart types)
- Data integrity validation (length matching, NaN/Infinity detection)
- Layout validation (best practices, performance warnings)

**To use this capability, read `abilities/echarts-validation.md` for detailed instructions.**

### 3. ECharts Visualization Generation

Generate interactive charts using `skills(echart)` embedded directly in Markdown.

**Chart Quantity Limitation:**
- **CRITICAL**: Generate **4-7 charts maximum** per report
- Focus on the most relevant, high-impact visualizations that directly address the user's question
- Avoid creating tangentially related charts that drift from the core analysis purpose
- Quality over quantity: each chart must provide clear, actionable insight

**Supported Chart Types:**
- **Line**: Trend analysis, time-series, multi-series comparison
- **Bar**: Categorical ranking, grouped/stacked comparisons
- **Scatter**: Correlation analysis, bubble charts, distribution patterns
- **Pie/Donut**: Composition, market share, proportional breakdown
- **Heatmap**: Correlation matrices, density patterns
- **Radar**: Multi-dimensional performance profiles
- **Funnel**: Conversion rates, process flow
- **Treemap**: Hierarchical part-to-whole relationships
- **Gauge**: KPI indicators, single metrics
- **Box Plot**: Statistical distributions, outlier detection
- **Candlestick**: Financial OHLC analysis

### 4. Insight Report Generation

Each report contains:
- **Executive Summary**: Key findings and recommendations overview
- **Data Profile**: Dataset characteristics and quality assessment
- **Key Insights**: Actionable findings with supporting visualizations
- **Chart Sections**: Interactive ECharts + detailed insights per chart
- **Recommendations**: Data-driven action items
- **Methodology Notes**: Analysis approach and assumptions

---

## CRITICAL WORKFLOW - MUST FOLLOW

### Chart Generation Protocol (MANDATORY)

**IMPORTANT: You MUST generate charts ONE BY ONE. Never generate all charts at once.**

The workflow is strictly sequential:

```
Data Loading → Analysis → Insight Planning
    │
    ├─► Read abilities/data-analysis.md if needed
    │
    ▼
Chart 1 → Generate → Validate (scripts/validate_echarts.py) → Fix (if needed) → Confirm
    ↓
Chart 2 → Generate → Validate → Fix (if needed) → Confirm
    ↓
Chart 3 → Generate → Validate → Fix (if needed) → Confirm
    ↓
... (continue for each chart)
    ↓
Final Insight Report → data_insight_report.md
```

---

## Phase 1: Data Loading & Profiling

### Step 1.1: Read Data Analysis Capability

**CRITICAL: Before performing data analysis, read the capability document:**

```markdown
Read `abilities/data-analysis.md` for:
- Script usage and parameters
- SQL query patterns
- Statistical summary generation
- Data export options
```

### Step 1.2: Load Data

```
1. Detect file format based on extension
2. Use scripts/analyze.py to load and inspect data:
   python scripts/analyze.py --files /path/to/data.xlsx --action inspect
3. Parse and validate data structure
```

### Step 1.3: Profile Data

Generate a data profile including:
- **Basic Info**: Row count, column count, file size
- **Column Analysis**: Data types, unique values, missing values per column
- **Data Quality**: Duplicate rows, null percentages, data type consistency
- **Statistical Summary**: For numeric columns (min, max, mean, median, std)
- **Sample Data**: First/last few rows for visual confirmation

**Use the analysis script:**
```bash
python scripts/analyze.py --files /path/to/data.xlsx --action summary --table Sheet1
```

### Step 1.4: Data Cleaning

Execute cleaning based on profile:
- Handle missing values (impute or remove)
- Remove duplicate records
- Convert data types as needed
- Detect and handle outliers
- Normalize text fields

---

## Phase 2: Insight Planning

1. Execute statistical analysis using `scripts/analyze.py`:
   - Descriptive statistics (mean, median, std, distribution)
   - Trend analysis (growth rates, seasonality, forecasts)
   - Correlation analysis (variable relationships)
   - Segmentation (group comparisons, rankings)

2. Plan 4-7 key charts to generate (create a plan, do NOT generate yet)

3. **Create an Insight Plan** - Document before generating:

```markdown
## 数据洞察计划

### 数据概况
- 总记录数: X
- 字段数: Y
- 时间范围: [如适用]
- 关键指标: [列出核心指标]

### 洞察方向
1. [洞察方向1 - 如: 销售趋势分析]
2. [洞察方向2 - 如: 产品类别表现]
3. [洞察方向3 - 如: 区域分布对比]
...

### 图表规划

| 序号 | 图表类型 | 图表标题 | 数据来源 | 核心洞察 | 业务价值 |
|------|----------|----------|----------|----------|----------|
| 1 | line | 销售额趋势 | 字段A, 字段B | 月度销售趋势 | 识别增长/下滑周期 |
| 2 | pie | 产品占比 | 字段C, 字段D | 产品销售占比 | 资源分配决策 |
| ... | ... | ... | ... | ... | ... |
```

---

## Phase 3: Sequential Chart Generation (STEP BY STEP)

### Step 3.1: Generate Chart 1

**Output to file**: `output_fs/charts/chart_01.md`

```markdown
# 图表 1: [图表标题]

## 可视化

```echarts
{
  "title": { "text": "[标题]" },
  "tooltip": { "trigger": "axis" },
  "legend": { "data": ["系列名称"] },
  "xAxis": { "type": "category", "data": ["分类1", "分类2"] },
  "yAxis": { "type": "value" },
  "series": [
    { "name": "系列名称", "type": "bar", "data": [100, 200] }
  ]
}
```

## 数据洞察

### 关键发现
- **发现1**: 描述数据中的关键模式
- **发现2**: 解释趋势或异常
- **发现3**: 对比分析结论

### 业务影响
- [业务影响描述]

### 行动建议
- [基于数据的可执行建议]

## 数据来源

- 原始数据: [文件名/Sheet名称]
- 数据范围: [具体字段或筛选条件]
- 数据处理: [如: 按月聚合/过滤异常值等]
```

### Step 3.2: Validate Chart 1 (MANDATORY - Use Validation Script)

**CRITICAL: After generating each chart, you MUST run the validation script.**

```bash
python scripts/validate_echarts.py output_fs/charts/chart_01.md
```

#### Validation Output Interpretation

The script outputs a structured report:

```markdown
## 校验报告 - [图表标题]

### JSON语法校验
- ✅/❌ JSON解析: [状态]
- ✅/❌ 引号检查: [状态]
- ✅/❌ 尾逗号检查: [状态]
- ✅/❌ 函数检查: [状态]

### ECharts结构校验
- ✅/❌ title字段: [状态]
- ✅/❌ tooltip字段: [状态]
- ✅/❌ series字段: [状态]
- ✅/❌ series[0].type: [状态]
- ✅/❌ series[0].data: [状态]

### 数据完整性校验
- ✅/❌ 数据长度匹配: [状态]
- ✅/❌ NaN检查: [状态]
- ✅/❌ Infinity检查: [状态]
- ✅/❌ 数值类型检查: [状态]

### 布局校验
- ✅/❌ grid配置: [状态]
- ✅/❌ 标题长度: [状态]
- ✅/❌ 图例项数: [状态]

### 校验结果
✅ 通过 / ❌ 失败 - X 个错误, Y 个警告
```

#### Validation Rules

| Category | Check | Level | Description |
|----------|-------|-------|-------------|
| JSON语法 | JSON解析 | ERROR | Valid JSON syntax |
| JSON语法 | 引号检查 | ERROR | Must use double quotes |
| JSON语法 | 尾逗号检查 | ERROR | No trailing commas |
| JSON语法 | 函数检查 | ERROR | No JavaScript functions |
| ECharts结构 | series字段 | ERROR | Required, non-empty array |
| ECharts结构 | series[].type | ERROR | Valid chart type |
| ECharts结构 | series[].data | ERROR | Must exist and be array |
| 数据完整性 | 数据长度匹配 | ERROR | xAxis/series data length match |
| 数据完整性 | NaN检查 | ERROR | No NaN values |
| 数据完整性 | Infinity检查 | ERROR | No Infinity values |
| 布局 | grid配置 | WARNING | Avoid complex positioning |
| 布局 | 标题长度 | WARNING | Under 30 characters |
| 布局 | 图例项数 | WARNING | Under 10 items |

### Step 3.3: Fix Issues (If Validation Fails)

**If the validation script reports errors, STOP and FIX immediately.**

Read `abilities/echarts-validation.md` for detailed fix instructions.

#### Quick Fix Reference

**Fix 1: JavaScript Functions → String Templates**
```javascript
// ❌ WRONG
"tooltip": { "formatter": function(params) { return params[0].name; } }

// ✅ CORRECT
"tooltip": { "formatter": "{b}: {c}" }
```

**Fix 2: Single Quotes → Double Quotes**
```javascript
// ❌ WRONG
{ 'name': 'Sales', 'type': 'bar' }

// ✅ CORRECT
{ "name": "Sales", "type": "bar" }
```

**Fix 3: Trailing Commas**
```javascript
// ❌ WRONG
"data": [1, 2, 3,],
"series": [{ "name": "A" },]

// ✅ CORRECT
"data": [1, 2, 3],
"series": [{ "name": "A" }]
```

**Fix 4: Data Length Mismatch**
```javascript
// ❌ WRONG: 3 categories but 4 data points
"xAxis": { "data": ["A", "B", "C"] },
"series": [{ "data": [10, 20, 30, 40] }]

// ✅ CORRECT: Align data
"xAxis": { "data": ["A", "B", "C", "D"] },
"series": [{ "data": [10, 20, 30, 40] }]
```

**Fix 5: Layout Issues**
```javascript
// ❌ WRONG: Overly complex manual positioning
"grid": { "left": "3%", "right": "4%", "bottom": "3%", "top": "15%" }

// ✅ CORRECT: Let ECharts handle it
"grid": { "containLabel": true }
```

**Fix 6: String Numbers**
```javascript
// ❌ WRONG: Numbers as strings
"data": ["100", "200", "300"]

// ✅ CORRECT: Actual numbers
"data": [100, 200, 300]
```

### Step 3.4: Re-validate After Fix

After fixing, run the validation script again:

```bash
python scripts/validate_echarts.py output_fs/charts/chart_01.md
```

Repeat until validation passes with `✅ 通过`.

### Step 3.5: Confirm and Proceed

After validation passes, record success and proceed to next chart:

```markdown
## 图表 1 完成 ✅
文件: output_fs/charts/chart_01.md
状态: 已校验通过
---
继续生成图表 2...
```

### Step 3.6: Repeat for Each Chart

Repeat steps 3.1-3.5 for each planned chart:
- Chart 2 → `output_fs/charts/chart_02.md`
- Chart 3 → `output_fs/charts/chart_03.md`
- ...
- Chart N → `output_fs/charts/chart_N.md`

---

## Phase 4: Final Insight Report Generation

After ALL charts are generated and validated individually:

### Step 4.1: Verify All Charts

Run validation on all charts:

```bash
python scripts/validate_echarts.py output_fs/charts/chart_01.md
python scripts/validate_echarts.py output_fs/charts/chart_02.md
python scripts/validate_echarts.py output_fs/charts/chart_03.md
# ... etc
```

Create status summary:

```markdown
## 图表完成状态汇总

| 图表 | 文件 | 状态 |
|------|------|------|
| 图表 1 | chart_01.md | ✅ 通过 |
| 图表 2 | chart_02.md | ✅ 通过 |
| 图表 3 | chart_03.md | ✅ 通过 |
| ... | ... | ... |
```

### Step 4.2: Generate Unified Insight Report

**Output to file**: `output_fs/data_insight_report.md`

Merge all charts and analytical insights into a single comprehensive report:

```markdown
# 数据洞察报告

## 执行摘要

[3-5句话概述核心发现和最重要的建议]

---

## 数据概况

### 基本信息

| 指标 | 数值 |
|------|------|
| 数据来源 | [文件名] |
| 总记录数 | X |
| 字段数 | Y |
| 时间范围 | YYYY-MM-DD ~ YYYY-MM-DD |
| 数据质量评分 | [高/中/低] |

### 关键指标概览

| 指标名称 | 当前值 | 变化趋势 | 备注 |
|----------|--------|----------|------|
| 指标1 | XXX | ↑/↓/→ | 说明 |
| 指标2 | XXX | ↑/↓/→ | 说明 |
| ... | ... | ... | ... |

---

## 核心洞察

### 洞察 1: [标题]

**发现**: [关键发现描述]

**数据支撑**: [具体数据]

**业务影响**: [对业务的实际影响]

**建议行动**: [可执行的具体建议]

### 洞察 2: [标题]

[同上结构]

---

## 数据可视化分析

本节包含 [N] 个交互式图表，展示数据分析的关键发现。

---

### 图表 1: [标题]

#### 可视化

```echarts
{ ... validated JSON ... }
```

#### 数据洞察

- **关键发现**: ...
- **趋势分析**: ...
- **业务建议**: ...

---

### 图表 2: [标题]

#### 可视化

```echarts
{ ... validated JSON ... }
```

#### 数据洞察

- **关键发现**: ...
- **趋势分析**: ...
- **业务建议**: ...

---

... (continue for all charts)

---

## 综合结论

### 核心洞察总结

1. [洞察1总结]
2. [洞察2总结]
3. [洞察3总结]

### 行动建议优先级

| 优先级 | 建议行动 | 预期影响 | 实施难度 |
|--------|----------|----------|----------|
| 高 | [建议1] | [影响描述] | 低/中/高 |
| 中 | [建议2] | [影响描述] | 低/中/高 |
| 低 | [建议3] | [影响描述] | 低/中/高 |

### 后续分析方向

- [可选的进一步分析建议1]
- [可选的进一步分析建议2]
- [可选的进一步分析建议3]

---

## 方法论

### 分析方法

[说明使用的分析方法和技术]

### 数据处理

[说明数据清洗和转换过程]

### 局限性

[说明分析的局限性和假设]

---

## 附录

### 数据质量报告

[数据质量详情]

### 技术细节

[补充技术信息]
```

---

## ECharts JSON Configuration Rules

**CRITICAL**: ECharts configurations MUST be valid JSON. They **MUST NOT** contain JavaScript functions.

### Prohibited Patterns

```javascript
// ❌ WRONG - Functions break JSON parsing
"tooltip": {
  "formatter": function(params) { return params[0].name; }
}
```

### Correct Patterns

```javascript
// ✅ CORRECT - Use string templates
"tooltip": {
  "formatter": "{b}: {c}"
}

// ✅ CORRECT - Or rely on default tooltip behavior
"tooltip": { "trigger": "axis" }
```

---

## Safe Chart Templates (Use These)

### Template 1: Bar Chart

```json
{
  "title": { "text": "图表标题" },
  "tooltip": { "trigger": "axis" },
  "legend": { "data": ["系列名称"] },
  "xAxis": { "type": "category", "data": ["类别1", "类别2", "类别3"] },
  "yAxis": { "type": "value" },
  "series": [{ "name": "系列名称", "type": "bar", "data": [100, 200, 300] }]
}
```

### Template 2: Line Chart

```json
{
  "title": { "text": "图表标题" },
  "tooltip": { "trigger": "axis" },
  "legend": { "data": ["系列名称"] },
  "xAxis": { "type": "category", "data": ["一月", "二月", "三月"] },
  "yAxis": { "type": "value" },
  "series": [{ "name": "系列名称", "type": "line", "data": [100, 200, 300] }]
}
```

### Template 3: Pie Chart

```json
{
  "title": { "text": "图表标题" },
  "tooltip": { "trigger": "item" },
  "legend": { "data": ["类别A", "类别B", "类别C"] },
  "series": [{
    "type": "pie",
    "radius": "50%",
    "data": [
      { "name": "类别A", "value": 100 },
      { "name": "类别B", "value": 200 },
      { "name": "类别C", "value": 300 }
    ]
  }]
}
```

### Template 4: Donut Chart

```json
{
  "title": { "text": "图表标题" },
  "tooltip": { "trigger": "item" },
  "legend": { "data": ["类别A", "类别B"] },
  "series": [{
    "type": "pie",
    "radius": ["40%", "70%"],
    "data": [
      { "name": "类别A", "value": 100 },
      { "name": "类别B", "value": 200 }
    ]
  }]
}
```

### Template 5: Grouped Bar Chart

```json
{
  "title": { "text": "图表标题" },
  "tooltip": { "trigger": "axis" },
  "legend": { "data": ["系列A", "系列B"] },
  "xAxis": { "type": "category", "data": ["类别1", "类别2", "类别3"] },
  "yAxis": { "type": "value" },
  "series": [
    { "name": "系列A", "type": "bar", "data": [100, 200, 300] },
    { "name": "系列B", "type": "bar", "data": [150, 250, 350] }
  ]
}
```

---

## Layout Rules (Simplified)

**CRITICAL PRINCIPLE: If unsure about layout, DO NOT configure it. Use ECharts defaults.**

### Core Rules

1. **Default is Best** - ECharts handles most layouts automatically. Only override when necessary.
2. **Minimal Configuration** - Only add layout properties you fully understand.
3. **Test Before Customizing** - If uncertain about positioning, omit the property entirely.

### When to Add Layout (Only if certain)

**Only add `grid` if:**
- Axis labels are being cut off AND you know the exact margin needed
- You need precise control over chart dimensions

**Safe grid configuration (use sparingly):**
```json
{ "grid": { "containLabel": true } }
```

**DO NOT manually set `left`, `right`, `top`, `bottom` unless you have verified the values work.**

### What NOT to Do

❌ DO NOT add layout properties "just in case"
❌ DO NOT copy complex layout configurations from examples without understanding them
❌ DO NOT try to fix overlap issues by guessing margin values

---

## Color Palette

Professional color palette for charts:
```json
{"color": ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de", "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc"]}
```

---

## Data Embedding

- Chart data arrays included directly in ECharts JSON configuration
- No external file references
- Use responsive width: 100% container
- Ensure data is properly escaped for JSON format

---

## Best Practices

1. **Chart Selection**: Choose chart type based on data characteristics
   - Trends over time → Line chart
   - Category comparison → Bar chart
   - Part-to-whole → Pie/Donut chart
   - Correlation → Scatter plot
   - Distribution → Box plot or histogram

2. **Chart Quantity Control** (CRITICAL):
   - **Generate 4-7 charts maximum** per report
   - Each chart must directly address the user's question or business objective
   - Do NOT create charts for data exploration purposes - focus on key insights
   - Avoid redundant visualizations showing similar information
   - When in doubt, prioritize relevance over completeness

3. **Sequential Generation** (MANDATORY):
   - Generate ONE chart at a time
   - Validate each chart with `scripts/validate_echarts.py` before proceeding
   - Fix any issues immediately
   - Merge only after all charts pass validation

4. **Validation** (MANDATORY):
   - **ALWAYS** run validation script after generating each chart
   - Fix all ERROR level issues before proceeding
   - Address WARNING level issues when possible
   - Re-validate after fixes

5. **Insight Quality**:
   - Every insight should be actionable
   - Support insights with specific data points
   - Connect findings to business impact
   - Provide clear recommendations

6. **Accessibility**: Include clear titles, labels, and legends
7. **Responsive Design**: Use percentage-based dimensions
8. **Color Consistency**: Use consistent colors for same categories across charts
9. **Data Labels**: Show values when precision matters

---

## Dependencies

Use these skills for implementation:
- `skills(spreadsheet)` - For Excel/CSV file reading and manipulation
- `skills(echart)` - For ECharts visualization generation

### Internal Capabilities

- **abilities/data-analysis.md** - SQL-based data analysis with DuckDB
- **abilities/echarts-validation.md** - ECharts configuration validation rules and fixes
- **scripts/analyze.py** - Data analysis script for inspecting, querying, and summarizing data
- **scripts/validate_echarts.py** - ECharts configuration validation script

---

## Example Usage

```
User: Analyze the sales data in data/sales.xlsx and create an insight report

Agent:
1. Read abilities/data-analysis.md for data analysis instructions
2. Load Excel file using scripts/analyze.py --action inspect
3. Profile data structure and quality using --action summary
4. Clean data (handle missing values, duplicates, outliers)
5. Execute statistical analysis with SQL queries
6. Create Insight Plan with 4-7 charts
7. FOR EACH chart (one by one):
   a. Generate chart_N.md with ECharts JSON
   b. Run: python scripts/validate_echarts.py output_fs/charts/chart_N.md
   c. Review validation report
   d. Fix any ERROR level issues
   e. Re-validate until ✅ 通过
   f. Confirm chart passes
8. Generate unified data_insight_report.md with:
   - Executive summary
   - Data profile
   - Key insights with business impact
   - All validated charts with insights
   - Prioritized action recommendations
   - Methodology and limitations
9. Save files to output_fs/
```

```
User: 分析 data/transactions.csv 文件，生成数据洞察报告

Agent:
1. 读取 abilities/data-analysis.md 了解数据分析方法
2. 使用 scripts/analyze.py 加载 CSV 文件
3. 分析数据结构和质量
4. 数据清洗和预处理
5. 执行探索性数据分析
6. 制定洞察计划（4-7个图表）
7. 逐个生成图表:
   a. 生成 chart_N.md
   b. 运行校验: python scripts/validate_echarts.py output_fs/charts/chart_N.md
   c. 查看校验报告
   d. 修复所有错误
   e. 重新校验直到通过
   f. 确认图表校验通过
8. 生成完整的数据洞察报告
9. 保存至 output_fs/data_insight_report.md
```

---

## Output Files Structure

```
output_fs/
├── charts/
│   ├── chart_01.md           # Individual chart (validated)
│   ├── chart_02.md           # Individual chart (validated)
│   ├── chart_03.md           # Individual chart (validated)
│   └── ...
└── data_insight_report.md    # Unified insight report with all charts and recommendations
```

---

## Changelog

### v1.3.0 (Current)
- Enhanced data-analysis capability with comprehensive pandas support
- Added pandas analysis patterns: data loading, cleaning, transformation, grouping, time series
- Added statistical analysis examples: correlation, trend analysis, outlier detection, segmentation
- Added decision guidance for when to use SQL script vs pandas code
- Updated capability assessment to cover all data analysis scenarios

### v1.2.0
- Added echarts-validation capability with dedicated ability document
- Added scripts/validate_echarts.py for automated chart validation
- Integrated validation script into chart generation workflow
- Added validation rules reference table
- Enhanced workflow to mandate script-based validation after each chart

### v1.1.0
- Integrated data-analysis capability with dedicated ability document
- Added scripts/analyze.py for SQL-based data analysis
- Added abilities/ directory for modular capability documentation
- Added capability assessment section with decision flow
- Added TSV file format support
- Enhanced data profiling with DuckDB SQL engine

### v1.0.0
- Initial release: Renamed from `excel-echarts-report` to `data-insight-report`
- Added support for multiple data formats (Excel, CSV, TSV, ODS)
- Enhanced data profiling and quality assessment
- Added structured insight planning phase
- Improved report structure with executive summary and prioritized recommendations

---

*Created for tabular data analysis with ECharts visualization*
*Version 1.3.0 - Enhanced pandas analysis with comprehensive statistical support*
