"""
Design tokens and the global Qt Style Sheet.

Single source of truth: the same dictionary is exposed to QML as the
`Theme` context property, so widgets and QML never drift apart.
"""

from string import Template

BG = "#0a0d14"
SURFACE = "#111722"
ELEVATED = "#192231"
HOVER = "#222d40"
BORDER = "#253044"
BORDER_STRONG = "#3b4a65"

TEXT = "#fafafa"
TEXT_DIM = "#aab6ca"
MUTED = "#75839a"

ACCENT = "#7487ff"
ACCENT_HOVER = "#9aa8ff"
ACCENT_SOFT = "#202a4b"

GREEN = "#34d399"
AMBER = "#fbbf24"
RED = "#f87171"

FONT_STACK = '"Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", sans-serif'

THEME_DICT = {
    "bg": BG, "surface": SURFACE, "elevated": ELEVATED, "hover": HOVER,
    "border": BORDER, "borderStrong": BORDER_STRONG,
    "text": TEXT, "textDim": TEXT_DIM, "muted": MUTED,
    "accent": ACCENT, "accentHover": ACCENT_HOVER, "accentSoft": ACCENT_SOFT,
    "green": GREEN, "amber": AMBER, "red": RED,
}

_QSS = Template("""
* { font-family: $font; font-size: 13px; color: $text; outline: none; }

QMainWindow, QDialog, QMessageBox { background: $bg; }
QWidget#Central, QFrame#WindowFrame { background: $bg; border: none; }
QStackedWidget#Stack { background: $bg; }
QToolTip { background: $elevated; color: $text; border: 1px solid $border; padding: 4px 8px; }

/* title bar */
QWidget#TitleBar { background: $bg; border-bottom: 1px solid $border; }
QLabel#TitleText { color: $textDim; font-size: 12px; }
QPushButton[chrome="true"] {
    background: transparent; border: none; border-radius: 0;
    min-width: 46px; max-width: 46px; min-height: 40px; max-height: 40px; padding: 0;
}
QPushButton[chrome="true"]:hover { background: $hover; }
QPushButton#CloseBtn:hover { background: #e5484d; }

/* sidebar */
QFrame#Sidebar { background: $surface; border: none; border-right: 1px solid $border; }
QLabel#Brand { font-size: 18px; font-weight: 600; color: $text; }
QLabel#SideGroup { color: $muted; font-size: 11px; padding: 10px 12px 4px 12px; }
QPushButton[nav="true"] {
    text-align: left; padding: 10px 12px; border: 1px solid transparent;
    border-radius: 8px; background: transparent; color: $textDim; font-size: 13px;
}
QPushButton[nav="true"]:hover { background: $elevated; color: $text; }
QPushButton[nav="true"]:checked {
    background: $accentSoft; border: 1px solid #303d68; border-left: 3px solid $accent;
    color: $accentHover; font-weight: 600; padding-left: 10px;
}

/* typography roles */
QLabel[role="h1"] { font-size: 26px; font-weight: 650; letter-spacing: -0.4px; }
QLabel[role="h2"] { font-size: 15px; font-weight: 650; color: $text; }
QLabel[role="dim"] { color: $textDim; }
QLabel[role="muted"] { color: $muted; font-size: 12px; }
QLabel[tone="good"] { color: $green; font-weight: 600; }
QLabel[tone="bad"] { color: $red; font-weight: 600; }
QLabel[tone="info"] { color: $accentHover; }

/* surfaces */
QFrame#Card { background: $surface; border: 1px solid $border; border-radius: 16px; }
QFrame#Card:hover { border-color: #303d55; }
QFrame#UnknownCard { background: $surface; border: 1px solid $border; border-radius: 10px; }
QFrame#UnknownCard:hover { border: 1px solid $borderStrong; }
QLabel#Thumb { background: $elevated; border-radius: 6px; color: $muted; }
QLabel#PhotoPreview { background: $elevated; border: 1px dashed $borderStrong; border-radius: 10px; color: $muted; }
QLabel#EmptyState { background: $surface; border: 1px dashed $borderStrong; border-radius: 16px; padding: 28px; color: $textDim; }

/* buttons */
QPushButton {
    background: $elevated; border: 1px solid $border; border-radius: 9px;
    padding: 8px 14px; min-height: 20px; color: $text;
}
QPushButton:hover { background: $hover; border: 1px solid $borderStrong; }
QPushButton:pressed { background: $surface; }
QPushButton:disabled { color: $muted; background: $surface; }
QPushButton[variant="primary"] { background: $accent; color: #ffffff; border: none; font-weight: 650; }
QPushButton[variant="primary"]:hover { background: $accentHover; }
QPushButton[variant="primary"]:disabled { background: #3f3f46; color: $muted; }
QPushButton[variant="accent"] { background: $accent; color: #ffffff; border: none; font-weight: 600; }
QPushButton[variant="accent"]:hover { background: $accentHover; }
QPushButton[variant="ghost"] { background: transparent; border: 1px solid transparent; color: $textDim; }
QPushButton[variant="ghost"]:hover { background: $elevated; color: $text; }
QPushButton[variant="danger"] { color: $red; }
QPushButton[variant="danger"]:hover { background: $red; color: $bg; border: 1px solid $red; }

/* inputs */
QLineEdit, QSpinBox {
    background: #0d121b; border: 1px solid $border; border-radius: 9px;
    padding: 9px 11px; selection-background-color: $accent;
}
QLineEdit:hover, QSpinBox:hover { border: 1px solid $borderStrong; }
QLineEdit:focus, QSpinBox:focus { border: 1px solid $accent; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QTextEdit#Log {
    background: #0c0c0f; border: 1px solid $border; border-radius: 8px;
    padding: 6px; font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace; font-size: 12px;
}

/* tables */
QTableWidget {
    background: $surface; border: 1px solid $border; border-radius: 12px;
    gridline-color: transparent; alternate-background-color: #0d121b;
    selection-background-color: $accentSoft; selection-color: $text;
}
QTableWidget::item { padding: 10px 8px; border: none; border-bottom: 1px solid $border; }
QTableWidget::item:selected { background: $accentSoft; color: $text; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background: $elevated; color: $textDim; padding: 11px 8px; border: none;
    border-bottom: 1px solid $border; font-weight: 500;
}
QTableCornerButton::section { background: $surface; border: none; }

/* calendar cells and session cards */
QPushButton[day="true"] {
    background: transparent; border: 1px solid transparent; border-radius: 10px;
    color: $textDim; padding: 0; font-size: 13px;
}
QPushButton[day="true"]:hover { background: $elevated; color: $text; }
QPushButton[day="true"][hasData="true"] { background: $accentSoft; color: $accentHover; font-weight: 600; }
QPushButton[day="true"][today="true"] { border: 1px solid $borderStrong; color: $text; }
QPushButton[day="true"]:checked { background: $text; color: $bg; font-weight: 600; border: none; }
QPushButton[day="true"]:disabled { background: transparent; border: none; color: transparent; }
QPushButton[sessionCard="true"] {
    text-align: left; padding: 12px 16px; border-radius: 10px; min-width: 150px;
    background: $surface; border: 1px solid $border; color: $textDim;
}
QPushButton[sessionCard="true"]:hover { border: 1px solid $borderStrong; }
QPushButton[sessionCard="true"]:checked { background: $accentSoft; border: 1px solid $accent; color: $text; font-weight: 600; }

/* scrolling */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $borderStrong; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border; border-radius: 3px; min-width: 28px; }
QScrollBar::handle:horizontal:hover { background: $borderStrong; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QStatusBar { background: $bg; color: $muted; border-top: 1px solid $border; }
""")


def build_stylesheet() -> str:
    mapping = {
        "bg": BG, "surface": SURFACE, "elevated": ELEVATED, "hover": HOVER,
        "border": BORDER, "borderStrong": BORDER_STRONG, "text": TEXT,
        "textDim": TEXT_DIM, "muted": MUTED, "accent": ACCENT,
        "accentHover": ACCENT_HOVER, "accentSoft": ACCENT_SOFT,
        "green": GREEN, "amber": AMBER, "red": RED, "font": FONT_STACK,
    }
    return _QSS.substitute(mapping)
