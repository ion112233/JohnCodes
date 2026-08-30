"""PyCharm "Darcula" colour scheme + Pygments token mapping."""
from __future__ import annotations

from pygments.token import Token

RGB = tuple[int, int, int]


def hx(s: str) -> RGB:
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


# ---- editor chrome (classic Darcula) ----
EDITOR_BG = hx("2B2B2B")
PANEL_BG = hx("3C3F41")
TOOLBAR_BG = hx("3C3F41")
TOOLSTRIP_BG = hx("393B3D")
GUTTER_BG = hx("313335")
BORDER = hx("2D2F30")
BORDER_LT = hx("4A4D4E")
CARET_ROW = hx("323232")
SELECTION = hx("214283")

LINE_NUMBER = hx("606366")
LINE_NUMBER_CUR = hx("A4A3A3")
CARET = hx("BBBBBB")
INDENT_GUIDE = hx("4B4B4C")
INDENT_GUIDE_CUR = hx("6A6A6B")
RIGHT_MARGIN = hx("2F2F2F")
VCS_ADDED = hx("4E7C4E")

TAB_ACTIVE_BG = hx("4E5254")
TAB_INACTIVE_BG = hx("3C3F41")
TAB_INACTIVE_FG = hx("9DA0A2")
TAB_UNDERLINE = hx("4E7EE8")

TITLE_FG = hx("BBBBBB")
ICON_FG = hx("AEB3B8")
ICON_DIM = hx("6E7174")
STATUS_FG = hx("8C8C8C")
TREE_FG = hx("BCBEC0")
TREE_SEL_BG = hx("2F65CA")
TREE_SEL_BG_INACTIVE = hx("4B4E50")
TREE_HEADER_FG = hx("8C8C8C")
FOLDER_ICON = hx("C2A05A")   # PyCharm's default manila folder

RUN_GREEN = hx("59A869")
DEBUG_GREEN = hx("6E9F5B")
STOP_RED = hx("C75450")

# ---- run / console panel ----
CONSOLE_CMD = hx("A9B7C6")
CONSOLE_OUT = hx("C7C7C7")
CONSOLE_OK = hx("5B9E5B")
TRAFFIC_RED = hx("FF5F57")
TRAFFIC_YELLOW = hx("FEBC2E")
TRAFFIC_GREEN = hx("28C840")

# ---- syntax ----
FG_DEFAULT = hx("A9B7C6")
KEYWORD = hx("CC7832")
BUILTIN = hx("8888C6")
SELF = hx("94558D")
FUNC = hx("FFC66D")
FUNC_MAGIC = hx("B200B2")
DECORATOR = hx("BBB529")
STRING = hx("6A8759")
DOCSTRING = hx("629755")
NUMBER = hx("6897BB")
COMMENT = hx("808080")
CONSTANT = hx("9876AA")

# ---- title / explain cards ----
CARD_BG = hx("1E1F22")
CARD_BG2 = hx("26282C")
CARD_FG = hx("DFE1E5")
CARD_MUTED = hx("8B8F98")
ACCENT = hx("3592C4")
ACCENT_GREEN = hx("6A8759")
ACCENT_ORANGE = hx("CC7832")
PILL_EASY = hx("57965C")
PILL_MEDIUM = hx("C0894A")
PILL_HARD = hx("C75450")

# (token prefix, colour, italic)
_RULES = [
    (Token.Comment, COMMENT, True),
    (Token.Keyword.Constant, CONSTANT, False),
    (Token.Keyword, KEYWORD, False),
    (Token.Operator.Word, KEYWORD, False),
    (Token.Name.Builtin.Pseudo, SELF, True),
    (Token.Name.Builtin, BUILTIN, False),
    (Token.Name.Function.Magic, FUNC_MAGIC, False),
    (Token.Name.Function, FUNC, False),
    (Token.Name.Decorator, DECORATOR, False),
    (Token.Name.Class, FG_DEFAULT, False),
    (Token.Name.Exception, BUILTIN, False),
    (Token.Name.Namespace, FG_DEFAULT, False),
    (Token.Literal.String.Doc, DOCSTRING, True),
    (Token.Literal.String.Escape, KEYWORD, False),
    (Token.Literal.String.Affix, KEYWORD, False),
    (Token.Literal.String, STRING, False),
    (Token.Literal.Number, NUMBER, False),
    (Token.Name.Constant, CONSTANT, False),
]


def token_style(tok) -> tuple[RGB, bool]:
    """Return (rgb, italic) for a Pygments token, walking up its parents."""
    for prefix, color, italic in _RULES:
        if tok in prefix:
            return color, italic
    return FG_DEFAULT, False
