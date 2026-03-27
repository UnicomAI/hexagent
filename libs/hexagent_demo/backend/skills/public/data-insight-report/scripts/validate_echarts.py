"""
ECharts Configuration Validator.

Validates ECharts JSON configurations for syntax, structure, data integrity, and layout.
Used in the data-insight-report workflow to ensure chart configurations are valid before
embedding in reports.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ValidationLevel(Enum):
    ERROR = "ERROR"      # Must fix - chart will not render
    WARNING = "WARNING"  # Should fix - may cause issues
    INFO = "INFO"        # Best practice suggestion


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    level: ValidationLevel
    category: str
    check: str
    status: bool
    message: str = ""


@dataclass
class ChartValidationReport:
    """Complete validation report for an ECharts configuration."""
    chart_title: str
    chart_type: str
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Check if all ERROR level validations passed."""
        return all(r.status or r.level != ValidationLevel.ERROR for r in self.results)

    @property
    def errors(self) -> list[ValidationResult]:
        """Get all ERROR level failures."""
        return [r for r in self.results if not r.status and r.level == ValidationLevel.ERROR]

    @property
    def warnings(self) -> list[ValidationResult]:
        """Get all WARNING level failures."""
        return [r for r in self.results if not r.status and r.level == ValidationLevel.WARNING]

    def add_result(self, level: ValidationLevel, category: str, check: str,
                   status: bool, message: str = "") -> None:
        """Add a validation result to the report."""
        self.results.append(ValidationResult(level, category, check, status, message))

    def to_markdown(self) -> str:
        """Generate a Markdown report."""
        lines = []
        lines.append(f"## 校验报告 - {self.chart_title}")
        lines.append("")

        # Group by category
        categories = {}
        for r in self.results:
            if r.category not in categories:
                categories[r.category] = []
            categories[r.category].append(r)

        for category, results in categories.items():
            lines.append(f"### {category}")
            for r in results:
                icon = "✅" if r.status else ("❌" if r.level == ValidationLevel.ERROR else "⚠️")
                lines.append(f"- {icon} {r.check}: {'通过' if r.status else r.message}")
            lines.append("")

        # Summary
        lines.append("### 校验结果")
        if self.passed:
            lines.append("✅ **通过**")
        else:
            lines.append(f"❌ **失败** - {len(self.errors)} 个错误, {len(self.warnings)} 个警告")
            if self.errors:
                lines.append("")
                lines.append("**需要修复的错误:**")
                for e in self.errors:
                    lines.append(f"- {e.check}: {e.message}")

        return "\n".join(lines)


# Valid ECharts chart types
VALID_CHART_TYPES = {
    "line", "bar", "pie", "scatter", "effectScatter", "radar", "tree",
    "treemap", "sunburst", "boxplot", "candlestick", "heatmap", "map",
    "parallel", "lines", "graph", "sankey", "funnel", "gauge", "pictorialBar",
    "themeRiver", "custom"
}

# Valid trigger types for tooltip
VALID_TOOLTIP_TRIGGERS = {"item", "axis", "none"}

# Recommended max lengths
MAX_TITLE_LENGTH = 30
MAX_LEGEND_ITEMS = 10
MAX_SERIES_ITEMS = 1000


def validate_json_syntax(config: str) -> tuple[dict | None, list[ValidationResult]]:
    """Validate JSON syntax and common issues."""
    results = []

    # Check 1: Parse as JSON
    try:
        data = json.loads(config)
        results.append(ValidationResult(
            ValidationLevel.ERROR, "JSON语法校验", "JSON解析", True
        ))
    except json.JSONDecodeError as e:
        results.append(ValidationResult(
            ValidationLevel.ERROR, "JSON语法校验", "JSON解析", False, f"Invalid JSON: {e}"
        ))
        return None, results

    # Check 2: No single quotes (should use double quotes)
    if "'" in config and '"' in config:
        # Mixed quotes
        results.append(ValidationResult(
            ValidationLevel.ERROR, "JSON语法校验", "引号检查", False,
            "Mixed single and double quotes detected"
        ))
    elif "'" in config and '"' not in config:
        # Only single quotes
        results.append(ValidationResult(
            ValidationLevel.ERROR, "JSON语法校验", "引号检查", False,
            "Use double quotes instead of single quotes"
        ))
    else:
        results.append(ValidationResult(
            ValidationLevel.INFO, "JSON语法校验", "引号检查", True
        ))

    # Check 3: No trailing commas
    trailing_comma_pattern = r',\s*[\]\}]'
    trailing_commas = re.findall(trailing_comma_pattern, config)
    if trailing_commas:
        results.append(ValidationResult(
            ValidationLevel.ERROR, "JSON语法校验", "尾逗号检查", False,
            f"Found {len(trailing_commas)} trailing comma(s)"
        ))
    else:
        results.append(ValidationResult(
            ValidationLevel.INFO, "JSON语法校验", "尾逗号检查", True
        ))

    # Check 4: No JavaScript functions
    function_patterns = [
        r'function\s*\(',
        r'=>\s*\{',
        r'=>\s*[^,\}\]]+\s*\(',
    ]
    has_function = False
    for pattern in function_patterns:
        if re.search(pattern, config):
            has_function = True
            break

    if has_function:
        results.append(ValidationResult(
            ValidationLevel.ERROR, "JSON语法校验", "函数检查", False,
            "JavaScript functions are not allowed in JSON"
        ))
    else:
        results.append(ValidationResult(
            ValidationLevel.INFO, "JSON语法校验", "函数检查", True, "无JavaScript函数"
        ))

    # Check 5: No undefined
    if "undefined" in config.lower():
        results.append(ValidationResult(
            ValidationLevel.ERROR, "JSON语法校验", "undefined检查", False,
            "'undefined' is not valid JSON"
        ))
    else:
        results.append(ValidationResult(
            ValidationLevel.INFO, "JSON语法校验", "undefined检查", True
        ))

    return data, results


def validate_echarts_structure(data: dict) -> list[ValidationResult]:
    """Validate ECharts configuration structure."""
    results = []

    # Check 1: Required fields
    has_title = "title" in data
    has_tooltip = "tooltip" in data
    has_series = "series" in data and isinstance(data.get("series"), list) and len(data["series"]) > 0

    if has_title:
        results.append(ValidationResult(
            ValidationLevel.INFO, "ECharts结构校验", "title字段", True
        ))
    else:
        results.append(ValidationResult(
            ValidationLevel.WARNING, "ECharts结构校验", "title字段", False,
            "Missing 'title' field (recommended)"
        ))

    if has_tooltip:
        results.append(ValidationResult(
            ValidationLevel.INFO, "ECharts结构校验", "tooltip字段", True
        ))
    else:
        results.append(ValidationResult(
            ValidationLevel.WARNING, "ECharts结构校验", "tooltip字段", False,
            "Missing 'tooltip' field (recommended)"
        ))

    if has_series:
        results.append(ValidationResult(
            ValidationLevel.INFO, "ECharts结构校验", "series字段", True
        ))
    else:
        results.append(ValidationResult(
            ValidationLevel.ERROR, "ECharts结构校验", "series字段", False,
            "Missing or empty 'series' field (required)"
        ))
        return results  # Can't continue without series

    # Check 2: Valid chart types
    series = data.get("series", [])
    chart_types = set()
    for i, s in enumerate(series):
        chart_type = s.get("type", "").lower()
        if chart_type:
            chart_types.add(chart_type)
            if chart_type in VALID_CHART_TYPES:
                results.append(ValidationResult(
                    ValidationLevel.INFO, "ECharts结构校验", f"series[{i}].type", True,
                    f"'{chart_type}' - 有效"
                ))
            else:
                results.append(ValidationResult(
                    ValidationLevel.ERROR, "ECharts结构校验", f"series[{i}].type", False,
                    f"'{chart_type}' is not a valid ECharts chart type"
                ))

    # Check 3: Data exists in series
    for i, s in enumerate(series):
        chart_type = s.get("type", "").lower()
        data_field = s.get("data")

        if data_field is None:
            results.append(ValidationResult(
                ValidationLevel.ERROR, "ECharts结构校验", f"series[{i}].data", False,
                "Missing 'data' field"
            ))
        elif not isinstance(data_field, list):
            results.append(ValidationResult(
                ValidationLevel.ERROR, "ECharts结构校验", f"series[{i}].data", False,
                "'data' must be an array"
            ))
        elif len(data_field) == 0:
            results.append(ValidationResult(
                ValidationLevel.WARNING, "ECharts结构校验", f"series[{i}].data", False,
                "'data' array is empty"
            ))
        else:
            results.append(ValidationResult(
                ValidationLevel.INFO, "ECharts结构校验", f"series[{i}].data", True,
                f"{len(data_field)} 个数据点"
            ))

    # Check 4: Axis configuration for bar/line charts
    needs_axis = chart_types & {"line", "bar", "scatter", "effectScatter", "boxplot", "candlestick"}
    if needs_axis:
        has_xaxis = "xAxis" in data
        has_yaxis = "yAxis" in data

        if has_xaxis:
            results.append(ValidationResult(
                ValidationLevel.INFO, "ECharts结构校验", "xAxis配置", True
            ))
        else:
            results.append(ValidationResult(
                ValidationLevel.ERROR, "ECharts结构校验", "xAxis配置", False,
                f"'{needs_axis}' charts require xAxis"
            ))

        if has_yaxis:
            results.append(ValidationResult(
                ValidationLevel.INFO, "ECharts结构校验", "yAxis配置", True
            ))
        else:
            results.append(ValidationResult(
                ValidationLevel.ERROR, "ECharts结构校验", "yAxis配置", False,
                f"'{needs_axis}' charts require yAxis"
            ))

    # Check 5: Pie chart data format
    if "pie" in chart_types:
        for i, s in enumerate(series):
            if s.get("type", "").lower() == "pie":
                pie_data = s.get("data", [])
                if pie_data and isinstance(pie_data, list) and len(pie_data) > 0:
                    # Check if data items have name and value
                    first_item = pie_data[0]
                    if isinstance(first_item, dict):
                        if "name" in first_item and "value" in first_item:
                            results.append(ValidationResult(
                                ValidationLevel.INFO, "ECharts结构校验", f"series[{i}] 饼图数据格式", True
                            ))
                        else:
                            results.append(ValidationResult(
                                ValidationLevel.WARNING, "ECharts结构校验", f"series[{i}] 饼图数据格式", False,
                                "Pie data items should have 'name' and 'value' properties"
                            ))

    return results


def validate_data_integrity(data: dict) -> list[ValidationResult]:
    """Validate data integrity and consistency."""
    results = []

    series = data.get("series", [])
    if not series:
        return results

    # Check xAxis data length matches series data length for bar/line
    x_axis = data.get("xAxis", {})
    if isinstance(x_axis, list):
        x_axis = x_axis[0] if x_axis else {}

    x_data = x_axis.get("data", []) if isinstance(x_axis, dict) else []

    for i, s in enumerate(series):
        chart_type = s.get("type", "").lower()
        s_data = s.get("data", [])

        if chart_type in {"line", "bar"} and x_data:
            if len(x_data) != len(s_data):
                results.append(ValidationResult(
                    ValidationLevel.ERROR, "数据完整性校验", f"series[{i}] 数据长度匹配", False,
                    f"xAxis has {len(x_data)} items, but series[{i}] has {len(s_data)} items"
                ))
            else:
                results.append(ValidationResult(
                    ValidationLevel.INFO, "数据完整性校验", f"series[{i}] 数据长度匹配", True
                ))

        # Check for NaN/Infinity in data
        if s_data:
            has_nan = False
            has_inf = False
            has_string_number = False

            for item in s_data:
                if isinstance(item, dict):
                    val = item.get("value")
                else:
                    val = item

                if isinstance(val, float):
                    import math
                    if math.isnan(val):
                        has_nan = True
                    if math.isinf(val):
                        has_inf = True
                elif isinstance(val, str) and val not in ("", None):
                    # Check if it's a string that looks like a number
                    try:
                        float(val)
                        has_string_number = True
                    except (ValueError, TypeError):
                        pass

            if has_nan:
                results.append(ValidationResult(
                    ValidationLevel.ERROR, "数据完整性校验", f"series[{i}] NaN检查", False,
                    "Data contains NaN values"
                ))
            else:
                results.append(ValidationResult(
                    ValidationLevel.INFO, "数据完整性校验", f"series[{i}] NaN检查", True
                ))

            if has_inf:
                results.append(ValidationResult(
                    ValidationLevel.ERROR, "数据完整性校验", f"series[{i}] Infinity检查", False,
                    "Data contains Infinity values"
                ))
            else:
                results.append(ValidationResult(
                    ValidationLevel.INFO, "数据完整性校验", f"series[{i}] Infinity检查", True
                ))

            if has_string_number:
                results.append(ValidationResult(
                    ValidationLevel.WARNING, "数据完整性校验", f"series[{i}] 数值类型检查", False,
                    "Some numeric values are strings, should be numbers"
                ))
            else:
                results.append(ValidationResult(
                    ValidationLevel.INFO, "数据完整性校验", f"series[{i}] 数值类型检查", True,
                    "所有数值为number类型"
                ))

    return results


def validate_layout(data: dict) -> list[ValidationResult]:
    """Validate layout configuration."""
    results = []

    # Check for overly complex grid configuration
    grid = data.get("grid", {})
    if grid:
        # Check for manual positioning
        manual_props = ["left", "right", "top", "bottom"]
        set_props = [p for p in manual_props if p in grid and grid[p]]

        if len(set_props) >= 3:
            results.append(ValidationResult(
                ValidationLevel.WARNING, "布局校验", "grid配置", False,
                f"Complex manual grid positioning ({', '.join(set_props)}), consider using containLabel: true instead"
            ))
        elif grid.get("containLabel"):
            results.append(ValidationResult(
                ValidationLevel.INFO, "布局校验", "grid配置", True, "使用 containLabel: true"
            ))
        else:
            results.append(ValidationResult(
                ValidationLevel.INFO, "布局校验", "grid配置", True, "使用默认布局"
            ))
    else:
        results.append(ValidationResult(
            ValidationLevel.INFO, "布局校验", "grid配置", True, "使用默认布局"
        ))

    # Check title length
    title = data.get("title", {})
    if isinstance(title, dict):
        title_text = title.get("text", "")
        if title_text:
            if len(title_text) > MAX_TITLE_LENGTH:
                results.append(ValidationResult(
                    ValidationLevel.WARNING, "布局校验", "标题长度", False,
                    f"Title is {len(title_text)} chars, consider keeping under {MAX_TITLE_LENGTH}"
                ))
            else:
                results.append(ValidationResult(
                    ValidationLevel.INFO, "布局校验", "标题长度", True, f"{len(title_text)}字符 - 合适"
                ))

    # Check legend items count
    legend = data.get("legend", {})
    if isinstance(legend, dict):
        legend_data = legend.get("data", [])
        if legend_data:
            if len(legend_data) > MAX_LEGEND_ITEMS:
                results.append(ValidationResult(
                    ValidationLevel.WARNING, "布局校验", "图例项数", False,
                    f"{len(legend_data)} items, consider keeping under {MAX_LEGEND_ITEMS}"
                ))
            else:
                results.append(ValidationResult(
                    ValidationLevel.INFO, "布局校验", "图例项数", True, f"{len(legend_data)}项 - 合理"
                ))

    # Check series data size
    series = data.get("series", [])
    for i, s in enumerate(series):
        s_data = s.get("data", [])
        if s_data and len(s_data) > MAX_SERIES_ITEMS:
            results.append(ValidationResult(
                ValidationLevel.WARNING, "布局校验", f"series[{i}] 数据量", False,
                f"{len(s_data)} items, large datasets may affect performance"
            ))

    return results


def validate_echarts_config(config: str | dict) -> ChartValidationReport:
    """
    Validate an ECharts configuration.

    Args:
        config: ECharts configuration as JSON string or dict

    Returns:
        ChartValidationReport with all validation results
    """
    # Parse config if string
    if isinstance(config, str):
        config_str = config
        data, syntax_results = validate_json_syntax(config_str)
    else:
        data = config
        config_str = json.dumps(config, ensure_ascii=False, indent=2)
        syntax_results = [ValidationResult(
            ValidationLevel.INFO, "JSON语法校验", "JSON解析", True, "已解析为dict对象"
        )]

    # Create report
    if data:
        chart_title = data.get("title", {}).get("text", "未命名图表")
        chart_type = data.get("series", [{}])[0].get("type", "unknown") if data.get("series") else "unknown"
    else:
        chart_title = "解析失败"
        chart_type = "unknown"

    report = ChartValidationReport(chart_title, chart_type)
    report.results.extend(syntax_results)

    if data is None:
        return report

    # Run all validations
    report.results.extend(validate_echarts_structure(data))
    report.results.extend(validate_data_integrity(data))
    report.results.extend(validate_layout(data))

    return report


def validate_file(file_path: str) -> ChartValidationReport:
    """
    Validate an ECharts configuration from a file.

    Args:
        file_path: Path to file containing ECharts JSON config

    Returns:
        ChartValidationReport with all validation results
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Try to extract echarts code block if present
    echarts_pattern = r'```echarts\s*\n(.*?)\n```'
    match = re.search(echarts_pattern, content, re.DOTALL)
    if match:
        config_str = match.group(1)
    else:
        config_str = content.strip()

    return validate_echarts_config(config_str)


def main():
    parser = argparse.ArgumentParser(
        description="Validate ECharts JSON configurations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a JSON file
  python validate_echarts.py config.json

  # Validate a Markdown file with echarts code block
  python validate_echarts.py chart.md

  # Validate JSON from stdin
  echo '{"title":{"text":"test"},"series":[{"type":"bar","data":[1,2,3]}]}' | python validate_echarts.py -

  # Output as JSON
  python validate_echarts.py config.json --format json
        """
    )
    parser.add_argument(
        "file",
        help="Path to file containing ECharts config (JSON or Markdown with ```echarts block), or '-' for stdin"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)"
    )
    parser.add_argument(
        "--strict", "-s",
        action="store_true",
        help="Exit with error code on any validation failure (including warnings)"
    )

    args = parser.parse_args()

    # Read input
    if args.file == "-":
        content = sys.stdin.read()
        # Try to extract echarts block
        echarts_pattern = r'```echarts\s*\n(.*?)\n```'
        match = re.search(echarts_pattern, content, re.DOTALL)
        config_str = match.group(1) if match else content.strip()
        report = validate_echarts_config(config_str)
    else:
        report = validate_file(args.file)

    # Output results
    if args.format == "json":
        output = {
            "chart_title": report.chart_title,
            "chart_type": report.chart_type,
            "passed": report.passed,
            "error_count": len(report.errors),
            "warning_count": len(report.warnings),
            "results": [
                {
                    "level": r.level.value,
                    "category": r.category,
                    "check": r.check,
                    "status": r.status,
                    "message": r.message
                }
                for r in report.results
            ]
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(report.to_markdown())

    # Exit code
    if not report.passed:
        sys.exit(1)
    if args.strict and report.warnings:
        sys.exit(2)


def setup_encoding():
    """Setup UTF-8 encoding for Windows console."""
    import sys
    import io
    if sys.platform == 'win32':
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass


if __name__ == "__main__":
    setup_encoding()
    main()
