from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# --- Unicode / whitespace normalization ------------------------------------

# Zero-width and related invisibles that often appear in scraped content
_ZERO_WIDTH = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\ufeff",  # BOM / zero-width no-break space
}

_SOFT_HYPHEN = "\u00ad"
_NBSP = "\u00a0"


def normalize_unicode_whitespace(text: str) -> str:
    """
    Normalize unicode oddities and whitespace without destroying paragraph breaks.

    - NFKC normalization
    - NBSP -> space
    - remove zero-width chars and soft hyphen
    - normalize CRLF/CR -> LF
    - strip trailing whitespace per line
    - collapse:
        * [ \\t\\f\\v]+ -> single space
        * 3+ newlines -> 2 newlines
    """
    s = text or ""
    if not s:
        return ""

    # Unicode normalization first
    try:
        s = unicodedata.normalize("NFKC", s)
    except Exception:
        # best-effort
        pass

    # Fix common whitespace / invisibles
    s = s.replace(_NBSP, " ")
    s = s.replace(_SOFT_HYPHEN, "")
    for ch in _ZERO_WIDTH:
        s = s.replace(ch, "")

    # Normalize newlines
    s = s.replace("\r\n", "\n").replace("\r", "\n")

    # Trim trailing whitespace on each line
    s = "\n".join([ln.rstrip() for ln in s.split("\n")])

    # Collapse runs of spaces/tabs (but keep newlines)
    s = re.sub(r"[ \t\f\v]+", " ", s)

    # Collapse excessive blank lines (keep paragraph breaks)
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()


# --- De-hyphenation --------------------------------------------------------

# Detect common "line-wrap hyphen" pattern, allowing an empty line created by
# removing soft-hyphen or other invisible chars:
#
#   inter-\n\nnational  -> international
#   inter-\n national   -> international
#
# Keep conservative: letters on both sides, left side >= 2 letters.
_DEHYPHEN_RX = re.compile(r"([A-Za-z]{2,})-\n(?:[ \t]*\n)?([A-Za-z])")


def dehyphenate_linewrap(text: str) -> str:
    """
    Remove hyphens that exist only because a word was wrapped at a line break.

    Example:
      "inter-\\nnational" -> "international"

    Conservative heuristic:
      - left side: at least 2 letters
      - right side: starts with a letter
      - requires a newline after the hyphen
      - allows one extra blank line (common after stripping invisibles)
    """
    s = text or ""
    if not s:
        return ""

    prev = None
    while prev != s:
        prev = s
        s = _DEHYPHEN_RX.sub(r"\1\2", s)
    return s


# --- UI / CTA line stripping ----------------------------------------------


def _norm_line_for_match(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").strip()).casefold()


# Small, high-precision set of "UI-ish" lines to drop if they appear alone.
# Keep this list conservative; you can expand later.
_DEFAULT_UI_LINE_PHRASES = (
    "download pdf",
    "article pdf",
    "open in new tab",
    "open in a new tab",
    "view full text",
    "view article",
    "metrics",
    "view metrics",
    "cite this article",
    "share",
    "sign in",
    "log in",
    "register",
    "cookies",
    "cookie preferences",
    "manage cookies",
    "privacy policy",
    "terms of use",
    "rights and permissions",
    "get access",
    "subscribe",
    "institutional access",
)


def strip_ui_lines(
    text: str,
    *,
    phrases: Iterable[str] = _DEFAULT_UI_LINE_PHRASES,
    max_line_len: int = 80,
) -> str:
    """
    Remove standalone UI/CTA junk lines.

    Rules:
      - works line-by-line
      - only drops lines that are short (<= max_line_len)
      - only drops if normalized line equals one of the known UI phrases
        OR starts with one of them (for small variants)
    """
    s = text or ""
    if not s:
        return ""

    norm_phrases = tuple(_norm_line_for_match(p) for p in phrases if (p or "").strip())
    out_lines: list[str] = []
    for ln in s.split("\n"):
        raw = ln.rstrip()
        norm = _norm_line_for_match(raw)

        drop = False
        if norm and len(raw.strip()) <= max_line_len:
            for p in norm_phrases:
                if norm == p or norm.startswith(p + " "):
                    drop = True
                    break

        if not drop:
            out_lines.append(raw)

    return "\n".join(out_lines).strip()


# --- Combined standardization ---------------------------------------------


def standardize_text(text: str) -> str:
    """
    Final pass you can apply to text artifacts.

    Order:
      1) unicode/whitespace normalize
      2) dehyphenate wrapped words
      3) strip standalone UI lines
      4) normalize again (to clean any artifacts from deletions)
    """
    s = normalize_unicode_whitespace(text)
    s = dehyphenate_linewrap(s)
    s = strip_ui_lines(s)
    s = normalize_unicode_whitespace(s)
    return s
