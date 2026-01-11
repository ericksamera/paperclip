from __future__ import annotations

from paperclip.text_standardize import (
    dehyphenate_linewrap,
    normalize_unicode_whitespace,
    standardize_text,
    strip_ui_lines,
)


def test_normalize_unicode_whitespace_removes_nbsp_zero_width_soft_hyphen():
    raw = "A\u00a0B\u200bC\u00adD\r\nE\rF"
    out = normalize_unicode_whitespace(raw)

    # NBSP becomes a normal space; zero-width + soft-hyphen are removed
    assert out == "A BCD\nE\nF"


def test_normalize_unicode_whitespace_collapses_spaces_and_excess_newlines():
    raw = "A   \t  B\n\n\n\nC"
    out = normalize_unicode_whitespace(raw)
    assert out == "A B\n\nC"


def test_dehyphenate_linewrap_removes_wrap_hyphen():
    raw = "inter-\nnational\nco-\noperate\nx-\ny"
    out = dehyphenate_linewrap(raw)

    assert "international" in out
    assert "cooperate" in out

    # left side "x" is 1 letter => should NOT dehyphenate
    assert "x-\ny" in out


def test_dehyphenate_linewrap_handles_blank_line_after_hyphen():
    # common after stripping soft-hyphens/zero-width characters on their own line
    raw = "inter-\n\nnational"
    out = dehyphenate_linewrap(raw)
    assert out == "international"


def test_strip_ui_lines_removes_known_short_ui_lines_only():
    raw = "\n".join(
        [
            "Introduction",
            "Open in new tab",
            "This is real content.",
            "Download PDF",
            "Conclusion",
        ]
    )
    out = strip_ui_lines(raw)
    assert "Open in new tab" not in out
    assert "Download PDF" not in out
    assert "This is real content." in out
    assert "Introduction" in out
    assert "Conclusion" in out


def test_standardize_text_combines_steps():
    raw = "inter-\n\u00ad\nnational\n\nOpen in new tab\n\nA\u00a0B\u200bC"
    out = standardize_text(raw)
    assert "international" in out
    assert "Open in new tab" not in out
    assert out.endswith("A BC")
