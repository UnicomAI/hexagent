# ECharts Validation Ability

## Overview

This ability provides automated validation for ECharts JSON configurations to ensure they are syntactically correct, structurally valid, and follow best practices before embedding in reports.

## Script Location

```
scripts/validate_echarts.py
```

## Core Capabilities

- **JSON Syntax Validation**: Detects common JSON errors (single quotes, trailing commas, functions, undefined)
- **ECharts Structure Validation**: Validates required fields and chart type configurations
- **Data Integrity Validation**: Checks data length consistency, NaN/Infinity values, type correctness
- **Layout Validation**: Warns about complex layouts and performance issues

## Usage

### Basic Usage

```bash
# Validate a JSON file
python scripts/validate_echarts.py chart_config.json

# Validate a Markdown file with echarts code block
python scripts/validate_echarts.py output_fs/charts/chart_01.md

# Validate JSON from stdin
echo '{"title":{"text":"test"},"series":[{"type":"bar","data":[1,2,3]}]}' | python scripts/validate_echarts.py -

# Output as JSON format
python scripts/validate_echarts.py chart_config.json --format json

# Strict mode (exit error on warnings too)
python scripts/validate_echarts.py chart_config.json --strict
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `file` | Path to file containing ECharts config (JSON or Markdown with ```echarts block), or `-` for stdin |
| `--format, -f` | Output format: `markdown` (default) or `json` |
| `--strict, -s` | Exit with error code on any validation failure (including warnings) |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All validations passed |
| 1 | One or more ERROR level failures |
| 2 | All passed but WARNING level failures (only with `--strict`) |

## Validation Categories

### 1. JSON Syntax Validation (JSON语法校验)

| Check | Level | Description |
|-------|-------|-------------|
| JSON解析 | ERROR | Valid JSON syntax |
| 引号检查 | ERROR | Must use double quotes, no single quotes |
| 尾逗号检查 | ERROR | No trailing commas in arrays/objects |
| 函数检查 | ERROR | No JavaScript functions allowed |
| undefined检查 | ERROR | No `undefined` values |

### 2. ECharts Structure Validation (ECharts结构校验)

| Check | Level | Description |
|-------|-------|-------------|
| title字段 | WARNING | Recommended to have title |
| tooltip字段 | WARNING | Recommended to have tooltip |
| series字段 | ERROR | Required, must be non-empty array |
| series[].type | ERROR | Must be valid ECharts chart type |
| series[].data | ERROR | Must exist and be array |
| xAxis/yAxis配置 | ERROR | Required for bar/line/scatter charts |
| 饼图数据格式 | WARNING | Pie data should have name/value |

### 3. Data Integrity Validation (数据完整性校验)

| Check | Level | Description |
|-------|-------|-------------|
| 数据长度匹配 | ERROR | xAxis data length must match series data length |
| NaN检查 | ERROR | No NaN values in data |
| Infinity检查 | ERROR | No Infinity values in data |
| 数值类型检查 | WARNING | Numeric values should be numbers, not strings |

### 4. Layout Validation (布局校验)

| Check | Level | Description |
|-------|-------|-------------|
| grid配置 | WARNING | Avoid complex manual positioning |
| 标题长度 | WARNING | Keep under 30 characters |
| 图例项数 | WARNING | Keep under 10 items |
| 数据量 | WARNING | Large datasets may affect performance |

## Output Formats

### Markdown Output (default)

```markdown
## 校验报告 - 销售趋势图

### JSON语法校验
- ✅ JSON解析: 通过
- ✅ 引号检查: 通过
- ✅ 尾逗号检查: 通过
- ✅ 函数检查: 无JavaScript函数

### ECharts结构校验
- ✅ title字段: 通过
- ✅ tooltip字段: 通过
- ✅ series字段: 通过
- ✅ series[0].type: 'bar' - 有效
- ✅ series[0].data: 12 个数据点

### 数据完整性校验
- ✅ series[0] 数据长度匹配: 通过
- ✅ series[0] NaN检查: 通过
- ✅ series[0] Infinity检查: 通过
- ✅ series[0] 数值类型检查: 所有数值为number类型

### 布局校验
- ✅ grid配置: 使用默认布局
- ✅ 标题长度: 5字符 - 合适
- ✅ 图例项数: 3项 - 合理

### 校验结果
✅ **通过**
```

### JSON Output (`--format json`)

```json
{
  "chart_title": "销售趋势图",
  "chart_type": "bar",
  "passed": true,
  "error_count": 0,
  "warning_count": 0,
  "results": [
    {
      "level": "INFO",
      "category": "JSON语法校验",
      "check": "JSON解析",
      "status": true,
      "message": ""
    }
  ]
}
```

## Integration with Data Insight Report Workflow

### When to Validate

**CRITICAL: Validate each chart immediately after generating it, before moving to the next chart.**

```
Generate Chart 1 → Validate Chart 1 → Fix Issues → Confirm Pass
                                                    ↓
                                          Generate Chart 2 → ...
```

### Validation Workflow

1. **Generate chart file** (e.g., `output_fs/charts/chart_01.md`)

2. **Run validation**:
   ```bash
   python scripts/validate_echarts.py output_fs/charts/chart_01.md
   ```

3. **Check result**:
   - If `✅ 通过`: Proceed to next chart
   - If `❌ 失败`: Review errors, fix the chart, re-validate

4. **Fix common issues**:
   - Single quotes → Double quotes
   - Trailing commas → Remove
   - JavaScript functions → Use string templates
   - String numbers → Convert to actual numbers
   - Data length mismatch → Align xAxis and series data

## Programmatic Usage

```python
from scripts.validate_echarts import validate_echarts_config, validate_file

# Validate from string
config = '''
{
  "title": { "text": "Sales" },
  "tooltip": { "trigger": "axis" },
  "xAxis": { "type": "category", "data": ["A", "B", "C"] },
  "yAxis": { "type": "value" },
  "series": [{ "type": "bar", "data": [100, 200, 300] }]
}
'''
report = validate_echarts_config(config)
print(report.to_markdown())
print(f"Passed: {report.passed}")

# Validate from file
report = validate_file("output_fs/charts/chart_01.md")
if not report.passed:
    for error in report.errors:
        print(f"ERROR: {error.check} - {error.message}")
```

## Common Error Fixes

### Fix 1: Single Quotes

```javascript
// ❌ WRONG
{ 'name': 'Sales', 'type': 'bar' }

// ✅ CORRECT
{ "name": "Sales", "type": "bar" }
```

### Fix 2: Trailing Commas

```javascript
// ❌ WRONG
"data": [1, 2, 3,],
"series": [{ "name": "A" },]

// ✅ CORRECT
"data": [1, 2, 3],
"series": [{ "name": "A" }]
```

### Fix 3: JavaScript Functions

```javascript
// ❌ WRONG
"tooltip": { "formatter": function(params) { return params[0].name; } }

// ✅ CORRECT
"tooltip": { "formatter": "{b}: {c}" }
```

### Fix 4: String Numbers

```javascript
// ❌ WRONG
"data": ["100", "200", "300"]

// ✅ CORRECT
"data": [100, 200, 300]
```

### Fix 5: Data Length Mismatch

```javascript
// ❌ WRONG: 3 categories but 4 data points
"xAxis": { "data": ["A", "B", "C"] },
"series": [{ "data": [10, 20, 30, 40] }]

// ✅ CORRECT: Align data
"xAxis": { "data": ["A", "B", "C", "D"] },
"series": [{ "data": [10, 20, 30, 40] }]
```

### Fix 6: Complex Layout

```javascript
// ❌ WRONG: Overly complex manual positioning
"grid": { "left": "3%", "right": "4%", "bottom": "3%", "top": "15%" }

// ✅ CORRECT: Let ECharts handle it
"grid": { "containLabel": true }
// Or remove grid entirely
```

## Notes

- The validator extracts ECharts config from Markdown files by looking for ```echarts code blocks
- Validation levels: ERROR (must fix), WARNING (should fix), INFO (passed)
- Use `--strict` flag to treat warnings as errors in CI/CD pipelines
- The script returns non-zero exit codes for use in automated workflows
