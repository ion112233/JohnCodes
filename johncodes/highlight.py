"""Syntax highlighting -> per-line coloured spans.

The full code is tokenised once. The typing animation then reveals a prefix of
these spans, so token colours never "jump" as characters appear.
"""
from __future__ import annotations

from dataclasses import dataclass

from pygments import lex
from pygments.lexers import PythonLexer

from . import theme

RGB = tuple[int, int, int]


@dataclass
class Span:
    text: str
    color: RGB
    italic: bool


Line = list[Span]


def highlight_python(code: str) -> list[Line]:
    lexer = PythonLexer(stripnl=False, ensurenl=False)
    lines: list[Line] = [[]]
    for tok, value in lex(code, lexer):
        color, italic = theme.token_style(tok)
        chunks = value.split("\n")
        for i, chunk in enumerate(chunks):
            if i > 0:
                lines.append([])
            if chunk:
                lines[-1].append(Span(chunk, color, italic))
    return lines


def prefix(lines: list[Line], n_chars: int) -> tuple[list[Line], tuple[int, int]]:
    """First ``n_chars`` characters of the code as spans.

    Returns (visible_lines, (caret_row, caret_col)).
    """
    out: list[Line] = [[]]
    budget = n_chars
    row = col = 0
    for li, line in enumerate(lines):
        if li > 0:
            out.append([])
            if budget <= 0:
                break
            budget -= 1  # the newline itself
        row = len(out) - 1
        col = 0
        for span in line:
            if budget <= 0:
                break
            take = min(len(span.text), budget)
            out[-1].append(Span(span.text[:take], span.color, span.italic))
            col += take
            budget -= take
        if budget <= 0:
            break
    return out, (row, col)


def total_chars(code: str) -> int:
    return len(code)
