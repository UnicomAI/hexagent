"""Tests for harness/skill_spec.py -- SKILL.md parsing and validation."""

from __future__ import annotations

import pytest

from hexagent.exceptions import SkillError, SkillParseError, SkillValidationError
from hexagent.harness.skill_spec import (
    SkillFrontmatter,
    SkillSpec,
    parse_skill_md,
    validate_skill_dir_name,
    validate_skill_name,
)

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_parse_error_is_skill_error(self) -> None:
        assert issubclass(SkillParseError, SkillError)

    def test_validation_error_is_skill_error(self) -> None:
        assert issubclass(SkillValidationError, SkillError)

    def test_validation_error_is_not_parse_error(self) -> None:
        assert not issubclass(SkillValidationError, SkillParseError)


# ---------------------------------------------------------------------------
# validate_skill_name
# ---------------------------------------------------------------------------


class TestValidateSkillName:
    def test_valid_simple_name(self) -> None:
        validate_skill_name("pdf")

    def test_valid_hyphenated_name(self) -> None:
        validate_skill_name("review-pr")

    def test_valid_multi_segment_name(self) -> None:
        validate_skill_name("my-cool-skill")

    def test_valid_with_digits(self) -> None:
        validate_skill_name("tool2")

    def test_valid_digits_only(self) -> None:
        validate_skill_name("123")

    def test_accepts_max_length_name(self) -> None:
        validate_skill_name("a" * 64)

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(SkillValidationError, match="must not be empty"):
            validate_skill_name("")

    def test_rejects_too_long_name(self) -> None:
        with pytest.raises(SkillValidationError, match="at most 64"):
            validate_skill_name("a" * 65)

    def test_rejects_uppercase(self) -> None:
        with pytest.raises(SkillValidationError, match="invalid"):
            validate_skill_name("PDF")

    def test_rejects_mixed_case(self) -> None:
        with pytest.raises(SkillValidationError, match="invalid"):
            validate_skill_name("mySkill")

    def test_rejects_leading_hyphen(self) -> None:
        with pytest.raises(SkillValidationError, match="invalid"):
            validate_skill_name("-pdf")

    def test_rejects_trailing_hyphen(self) -> None:
        with pytest.raises(SkillValidationError, match="invalid"):
            validate_skill_name("pdf-")

    def test_rejects_consecutive_hyphens(self) -> None:
        with pytest.raises(SkillValidationError, match="invalid"):
            validate_skill_name("pdf--tool")

    def test_rejects_underscores(self) -> None:
        with pytest.raises(SkillValidationError, match="invalid"):
            validate_skill_name("pdf_tool")

    def test_rejects_dots(self) -> None:
        with pytest.raises(SkillValidationError, match="invalid"):
            validate_skill_name("pdf.tool")

    def test_rejects_spaces(self) -> None:
        with pytest.raises(SkillValidationError, match="invalid"):
            validate_skill_name("pdf tool")


# ---------------------------------------------------------------------------
# validate_skill_dir_name
# ---------------------------------------------------------------------------


class TestValidateSkillDirName:
    def test_matching_names(self) -> None:
        validate_skill_dir_name("pdf", "pdf")

    def test_matching_hyphenated_names(self) -> None:
        validate_skill_dir_name("my-skill", "my-skill")

    def test_mismatch_raises(self) -> None:
        with pytest.raises(SkillValidationError, match="does not match directory"):
            validate_skill_dir_name("pdf-tool", "pdf-processing")

    def test_case_mismatch_raises(self) -> None:
        with pytest.raises(SkillValidationError, match="does not match directory"):
            validate_skill_dir_name("pdf", "PDF")


# ---------------------------------------------------------------------------
# parse_skill_md -- valid inputs
# ---------------------------------------------------------------------------


class TestParseSkillMdValid:
    def test_minimal(self) -> None:
        raw = "---\nname: pdf\ndescription: Extract text from PDFs\n---\n# Instructions\n"
        spec = parse_skill_md(raw)
        assert spec.frontmatter.name == "pdf"
        assert spec.frontmatter.description == "Extract text from PDFs"
        assert "# Instructions" in spec.body
        assert spec.frontmatter.license is None
        assert spec.frontmatter.compatibility is None
        assert spec.frontmatter.metadata == {}

    def test_all_fields(self) -> None:
        raw = """\
---
name: pdf-processing
description: Extract PDF text, fill forms, merge files.
license: Apache-2.0
compatibility: Requires poppler-utils
metadata:
  author: example-org
  version: "1.0"
---
# PDF Processing

Step-by-step instructions here.
"""
        spec = parse_skill_md(raw)
        assert spec.frontmatter.name == "pdf-processing"
        assert spec.frontmatter.description == "Extract PDF text, fill forms, merge files."
        assert spec.frontmatter.license == "Apache-2.0"
        assert spec.frontmatter.compatibility == "Requires poppler-utils"
        assert spec.frontmatter.metadata == {"author": "example-org", "version": "1.0"}
        assert "Step-by-step instructions" in spec.body

    def test_empty_body(self) -> None:
        raw = "---\nname: pdf\ndescription: Handles PDFs\n---\n"
        spec = parse_skill_md(raw)
        assert spec.body == ""

    def test_multiline_description(self) -> None:
        raw = """\
---
name: pdf
description: >
  A long description
  that spans multiple lines.
---
Body.
"""
        spec = parse_skill_md(raw)
        assert "A long description" in spec.frontmatter.description
        assert "multiple lines." in spec.frontmatter.description

    def test_block_scalar_description(self) -> None:
        raw = """\
---
name: pdf
description: |
  Line one.
  Line two.
---
Body.
"""
        spec = parse_skill_md(raw)
        assert "Line one." in spec.frontmatter.description
        assert "Line two." in spec.frontmatter.description

    def test_quoted_values(self) -> None:
        raw = '---\nname: "my-skill"\ndescription: "A skill"\n---\nBody.'
        spec = parse_skill_md(raw)
        assert spec.frontmatter.name == "my-skill"
        assert spec.frontmatter.description == "A skill"

    def test_description_with_colons(self) -> None:
        raw = '---\nname: web\ndescription: "Fetch URL: https://example.com:8080"\n---\nBody.'
        spec = parse_skill_md(raw)
        assert "https://example.com:8080" in spec.frontmatter.description

    def test_body_preserves_formatting(self) -> None:
        body_content = "# Header\n\n- bullet 1\n- bullet 2\n\n```python\nprint('hi')\n```"
        raw = f"---\nname: pdf\ndescription: PDFs\n---\n{body_content}\n"
        spec = parse_skill_md(raw)
        assert "```python" in spec.body
        assert "- bullet 1" in spec.body

    def test_frontmatter_with_dashes_in_body(self) -> None:
        raw = "---\nname: pdf\ndescription: PDFs\n---\nSome text\n---\nMore text after dashes."
        spec = parse_skill_md(raw)
        assert "---" in spec.body
        assert "More text after dashes." in spec.body

    def test_leading_whitespace_stripped(self) -> None:
        raw = "\n\n---\nname: pdf\ndescription: PDFs\n---\nBody."
        spec = parse_skill_md(raw)
        assert spec.frontmatter.name == "pdf"


# ---------------------------------------------------------------------------
# parse_skill_md -- structural errors (SkillParseError)
# ---------------------------------------------------------------------------


class TestParseSkillMdParseErrors:
    def test_missing_opening_delimiter(self) -> None:
        with pytest.raises(SkillParseError, match="must start with"):
            parse_skill_md("name: pdf\ndescription: PDFs\n---\nBody.")

    def test_missing_closing_delimiter(self) -> None:
        with pytest.raises(SkillParseError, match="missing closing"):
            parse_skill_md("---\nname: pdf\ndescription: PDFs\n")

    def test_empty_input(self) -> None:
        with pytest.raises(SkillParseError):
            parse_skill_md("")

    def test_empty_frontmatter(self) -> None:
        with pytest.raises(SkillParseError, match="frontmatter is empty"):
            parse_skill_md("---\n---\nBody.")

    def test_whitespace_only_frontmatter(self) -> None:
        with pytest.raises(SkillParseError, match="frontmatter is empty"):
            parse_skill_md("---\n  \n\n---\nBody.")

    def test_invalid_yaml(self) -> None:
        raw = "---\n: invalid: yaml: [unterminated\n---\nBody."
        with pytest.raises(SkillParseError, match="Invalid YAML"):
            parse_skill_md(raw)

    def test_yaml_not_a_mapping(self) -> None:
        raw = "---\n- a list\n- not a mapping\n---\nBody."
        with pytest.raises(SkillParseError, match="must be a YAML mapping"):
            parse_skill_md(raw)

    def test_missing_name(self) -> None:
        with pytest.raises(SkillParseError, match="missing required field.*name"):
            parse_skill_md("---\ndescription: Some description\n---\nBody.")

    def test_missing_description(self) -> None:
        with pytest.raises(SkillParseError, match="missing required field.*description"):
            parse_skill_md("---\nname: pdf\n---\nBody.")


# ---------------------------------------------------------------------------
# parse_skill_md -- validation errors (SkillValidationError)
# ---------------------------------------------------------------------------


class TestParseSkillMdValidationErrors:
    def test_invalid_name_uppercase(self) -> None:
        with pytest.raises(SkillValidationError):
            parse_skill_md("---\nname: PDF\ndescription: PDFs\n---\nBody.")

    def test_invalid_name_consecutive_hyphens(self) -> None:
        with pytest.raises(SkillValidationError):
            parse_skill_md("---\nname: pdf--tool\ndescription: PDFs\n---\nBody.")

    def test_description_too_long(self) -> None:
        desc = "x" * 1025
        with pytest.raises(SkillValidationError, match="at most 1024"):
            parse_skill_md(f"---\nname: pdf\ndescription: {desc}\n---\nBody.")

    def test_empty_description(self) -> None:
        with pytest.raises(SkillValidationError, match="must not be empty"):
            parse_skill_md('---\nname: pdf\ndescription: ""\n---\nBody.')

    def test_compatibility_too_long(self) -> None:
        compat = "x" * 501
        raw = f"---\nname: pdf\ndescription: PDFs\ncompatibility: {compat}\n---\nBody."
        with pytest.raises(SkillValidationError, match="at most 500"):
            parse_skill_md(raw)

    def test_metadata_non_string_value(self) -> None:
        raw = "---\nname: pdf\ndescription: PDFs\nmetadata:\n  count: 123\n---\nBody."
        with pytest.raises(SkillValidationError, match="must be a string"):
            parse_skill_md(raw)

    def test_metadata_not_a_mapping(self) -> None:
        raw = "---\nname: pdf\ndescription: PDFs\nmetadata: just-a-string\n---\nBody."
        with pytest.raises(SkillValidationError, match="must be a mapping"):
            parse_skill_md(raw)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


class TestSkillFrontmatter:
    def test_frozen(self) -> None:
        fm = SkillFrontmatter(name="pdf", description="PDFs")
        with pytest.raises(AttributeError):
            fm.name = "other"  # type: ignore[misc]

    def test_defaults(self) -> None:
        fm = SkillFrontmatter(name="pdf", description="PDFs")
        assert fm.license is None
        assert fm.compatibility is None
        assert fm.metadata == {}


class TestSkillSpec:
    def test_frozen(self) -> None:
        fm = SkillFrontmatter(name="pdf", description="PDFs")
        spec = SkillSpec(frontmatter=fm, body="Body.")
        with pytest.raises(AttributeError):
            spec.body = "other"  # type: ignore[misc]

    def test_equality(self) -> None:
        fm = SkillFrontmatter(name="pdf", description="PDFs")
        a = SkillSpec(frontmatter=fm, body="Body.")
        b = SkillSpec(frontmatter=fm, body="Body.")
        assert a == b

    def test_inequality_body(self) -> None:
        fm = SkillFrontmatter(name="pdf", description="PDFs")
        a = SkillSpec(frontmatter=fm, body="Body A.")
        b = SkillSpec(frontmatter=fm, body="Body B.")
        assert a != b

    def test_inequality_frontmatter(self) -> None:
        a = SkillSpec(
            frontmatter=SkillFrontmatter(name="pdf", description="PDFs"),
            body="Body.",
        )
        b = SkillSpec(
            frontmatter=SkillFrontmatter(name="other", description="PDFs"),
            body="Body.",
        )
        assert a != b
