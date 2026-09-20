"""Protects {_variable} placeholders across a round trip through a translation engine.

A translator can glue text against an inline marker (observed with Google
Translate producing ":counttask" from ":count" + "task"), so the round trip
is verified, not trusted: mismatched output is reported to the caller instead
of being silently shipped.

The internal marker is a nonsense word (QWXJZiZJXWQ), not bracket-and-digit
punctuation and not a real-looking word: Cloudflare's m2m100 mangled or
dropped "[[[0]]]" outright, and Google partially re-cased a word-shaped
marker built from real substrings like "PLACEHOLDER" (both verified live).
A string with no dictionary substring is copied through untouched by both.
"""

import re

PLACEHOLDER_PATTERN = re.compile(r"\{_.*?\}")
MARKER_PATTERN = re.compile(r"\{_\w+\}")


def protect(text: str) -> tuple[str, list[str]]:
    if not isinstance(text, str):
        return text, []
    placeholders = PLACEHOLDER_PATTERN.findall(text)
    protected_text = text
    for i, p in enumerate(placeholders):
        protected_text = protected_text.replace(p, f" QWXJZ{i}ZJXWQ ")
    return protected_text, placeholders


def restore(text: str, placeholders: list[str]) -> str:
    """Puts each {_var} back where its [[[i]]] marker was.

    A translator is free to add or drop whitespace around the marker
    (Google does both depending on context), so any whitespace found next to
    it is normalized to a single space rather than dropped: dropping it is
    what glued the restored placeholder straight onto the surrounding word.
    """
    if not isinstance(text, str):
        return text
    restored_text = text
    for i, p in enumerate(placeholders):
        pattern = re.compile(rf"(\s*)QWXJZ{i}ZJXWQ(\s*)")
        restored_text = pattern.sub(
            lambda m, p=p: (" " if m.group(1) else "") + p + (" " if m.group(2) else ""),
            restored_text,
        )
    return re.sub(r"\s+([.,])", r"\1", restored_text)


GLUED_PATTERN = re.compile(r"[\w:]\{_\w+\}|\{_\w+\}\w")


def survived_intact(original: str, translated: str) -> bool:
    """True if translated has the same {_var} tokens as original, each still word-boundary separated.

    The token set alone is not enough: a translator can leave "{_name}" intact
    while gluing it straight onto the previous word ("Hallo{_name}"), which
    the token-only check would miss entirely.
    """
    same_tokens = sorted(MARKER_PATTERN.findall(original)) == sorted(MARKER_PATTERN.findall(translated))
    return same_tokens and not GLUED_PATTERN.search(translated)
