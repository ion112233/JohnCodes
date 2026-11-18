"""LeetCode (dark theme) colours + a Monaco-style Python highlighter."""
from __future__ import annotations

from pygments import lex
from pygments.lexers import PythonLexer
from pygments.token import Token

from .highlight import Line, Span
from .theme import hx

PAGE_BG = hx("0A0A0A")
NAV_BG = hx("1A1A1A")
PANEL_BG = hx("1A1A1A")
BAR_BG = hx("282828")
EDITOR_BG = hx("1E1E1E")
LINE = hx("3A3A3A")
TEXT = hx("BEC0C4")          # body copy (rgba(239,241,246,.75) on panel)
TEXT_STRONG = hx("EFF1F6")
MUTED = hx("8A8D93")
CHIP_BG = hx("2E2E2E")
CHIP_LINE = hx("383838")
ORANGE = hx("FFA116")
GREEN = hx("2CBB5D")
GREEN_TXT = hx("2CBB5D")
RED = hx("FF375F")
EASY = hx("00B8A3")
EASY_BG = hx("12332F")
MED = hx("FFB800")
HARD = hx("FF375F")
BTN_BG = hx("333333")
GUTTER = hx("858585")
SELECT = hx("264F78")
CONSOLE_BG = hx("262626")
BOX_BG = hx("333333")

# Monaco "vs-dark"
KEYWORD = hx("569CD6")
CONTROL = hx("C586C0")
FUNC = hx("DCDCAA")
CLASS = hx("4EC9B0")
STRING = hx("CE9178")
NUMBER = hx("B5CEA8")
COMMENT = hx("6A9955")
DEFAULT = hx("D4D4D4")
PARAM = hx("9CDCFE")
BUILTIN = hx("DCDCAA")

_CONTROL_KW = {"if", "elif", "else", "for", "while", "return", "break", "continue", "in", "not",
               "and", "or", "import", "from", "try", "except", "finally", "raise", "with",
               "yield", "pass", "assert", "is"}


def token_style(tok, value: str):
    if tok in Token.Comment:
        return COMMENT, False
    if tok in Token.Literal.String.Doc:
        return COMMENT, False
    if tok in Token.Literal.String:
        return STRING, False
    if tok in Token.Literal.Number:
        return NUMBER, False
    if tok in Token.Keyword.Constant:
        return KEYWORD, False
    if tok in Token.Keyword or tok in Token.Operator.Word:
        return (CONTROL if value in _CONTROL_KW else KEYWORD), False
    if tok in Token.Name.Class:
        return CLASS, False
    if tok in Token.Name.Function:
        return FUNC, False
    if tok in Token.Name.Builtin.Pseudo:
        return PARAM, False
    if tok in Token.Name.Builtin:
        return BUILTIN, False
    return DEFAULT, False


def highlight(code: str) -> list[Line]:
    lexer = PythonLexer(stripnl=False, ensurenl=False)
    lines: list[Line] = [[]]
    for tok, value in lex(code, lexer):
        color, italic = token_style(tok, value)
        for i, chunk in enumerate(value.split("\n")):
            if i > 0:
                lines.append([])
            if chunk:
                lines[-1].append(Span(chunk, color, italic))
    return lines
