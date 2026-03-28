"""Tests for markdown text processing utilities."""

from clawwork.tools.web._markdown import strip_links_and_images


class TestStripLinksAndImages:
    """Tests for strip_links_and_images function."""

    # Basic transformations

    def test_converts_link_to_plain_text(self) -> None:
        assert strip_links_and_images("[click](https://example.com)") == "click"

    def test_removes_image_entirely(self) -> None:
        assert strip_links_and_images("![alt](https://example.com/img.png)") == ""

    def test_handles_mixed_content(self) -> None:
        text = "See ![icon](x.png) and [click](url) here"
        assert strip_links_and_images(text) == "See  and click here"

    # URL edge cases

    def test_handles_url_with_parentheses(self) -> None:
        text = "[Python](https://en.wikipedia.org/wiki/Python_(language))"
        assert strip_links_and_images(text) == "Python"

    def test_handles_url_with_query_params(self) -> None:
        assert strip_links_and_images("[link](https://x.com?a=1&b=2)") == "link"

    # Code block protection

    def test_preserves_link_syntax_in_inline_code(self) -> None:
        text = "Use `[text](url)` for links"
        assert strip_links_and_images(text) == "Use `[text](url)` for links"

    def test_preserves_link_syntax_in_fenced_code_block(self) -> None:
        text = "Example:\n```\n[link](url)\n```\nEnd"
        assert strip_links_and_images(text) == "Example:\n```\n[link](url)\n```\nEnd"

    def test_preserves_link_syntax_in_tilde_code_block(self) -> None:
        text = "~~~\n[link](url)\n~~~"
        assert strip_links_and_images(text) == "~~~\n[link](url)\n~~~"

    def test_mixed_real_and_code_block_links(self) -> None:
        text = "[real](url) and ```\n[fake](url)\n```"
        assert strip_links_and_images(text) == "real and ```\n[fake](url)\n```"

    # Nested image in link

    def test_removes_nested_image_in_link(self) -> None:
        assert strip_links_and_images("[![img](i.png)](url)") == ""

    # Empty/edge inputs

    def test_returns_empty_string_for_empty_input(self) -> None:
        assert strip_links_and_images("") == ""

    def test_returns_none_for_none_input(self) -> None:
        assert strip_links_and_images(None) is None  # type: ignore[arg-type]

    def test_preserves_plain_text(self) -> None:
        assert strip_links_and_images("Just plain text") == "Just plain text"

    def test_preserves_brackets_without_url(self) -> None:
        assert strip_links_and_images("[not a link]") == "[not a link]"
