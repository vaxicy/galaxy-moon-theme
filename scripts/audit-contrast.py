# -*- coding: utf-8 -*-
"""Audit WCAG 2.x contrast for every foreground/background pair a VS Code theme renders.

Checks, per variant:
  * workbench text pairs (label, side bar, tabs, lists, inputs, widgets, badges, bars)
  * workbench UI pairs (focus border, cursor, bracket match, indent guides, borders)
  * TextMate token colors and semantic tokens on the editor background
  * token colors on the current line / selection / find match (warning level)
  * the 16 color ANSI palette on the terminal background

Bars: text = 4.5:1 (WCAG AA), UI = 3.0:1 (WCAG 1.4.11), decorative = report only.
Token colors on a *temporary* highlight (selection, current line, find match) are
reported as warnings - VS Code draws those on purpose and they are never the only
way to read the code.

Usage:
    python3 scripts/audit-contrast.py            # exit 1 if any hard check fails
    python3 scripts/audit-contrast.py -v         # also list the passing pairs
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

THEMES = [
    ("Light", "themes/galaxy-moon-theme-light-color-theme.json"),
    ("Dark", "themes/galaxy-moon-theme-dark-color-theme.json"),
]

TEXT = 4.5          # normal body text
UI = 3.0            # non text UI element (WCAG 1.4.11)
WARN = 3.0          # token color on a temporary highlight

# ANSI black is meant to be invisible on a dark canvas and is not a readability
# target; it is listed but never fails the run.
ANSI_SKIP = {"terminal.ansiBlack"}


# ------------------------------------------------------------------ color math
def parse(value):
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    a = int(s[6:8], 16) / 255.0 if len(s) >= 8 else 1.0
    return (r, g, b, a)


def flatten(fg, bg):
    r, g, b, a = fg
    return (round(r * a + bg[0] * (1 - a)), round(g * a + bg[1] * (1 - a)),
            round(b * a + bg[2] * (1 - a)), 1.0)


def luminance(rgb):
    def channel(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(x) for x in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg_hex, bg_hex, parent_hex="#222122"):
    """Composite translucent colors over their real parent before measuring.

    A translucent *background* (for example list.inactiveSelectionBackground
    #CCCCCC99) is drawn on top of the editor canvas, never on top of black, so the
    parent has to be the theme's editor background instead of a made up dark grey.
    """
    fg, bg = parse(fg_hex), parse(bg_hex)
    if bg[3] < 1.0:
        bg = flatten(bg, parse(parent_hex))
    if fg[3] < 1.0:
        fg = flatten(fg, bg)
    a, b = luminance(fg), luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# ------------------------------------------------------------------ check list
# (label, fg key, bg key, bar, fallback fg key when the fg is not defined)
TEXT_PAIRS = [
    ("workbench foreground", "foreground", "editor.background", TEXT, None),
    ("editor foreground", "editor.foreground", "editor.background", TEXT, None),
    ("side bar", "sideBar.foreground", "sideBar.background", TEXT, None),
    ("activity bar", "activityBar.foreground", "activityBar.background", TEXT, None),
    ("activity bar inactive", "activityBar.inactiveForeground", "activityBar.background", TEXT, None),
    ("panel", "panel.foreground", "panel.background", TEXT, None),
    ("tab active", "tab.activeForeground", "tab.activeBackground", TEXT, None),
    ("tab inactive", "tab.inactiveForeground", "tab.inactiveBackground", TEXT, None),
    ("list active selection", "list.activeSelectionForeground", "list.activeSelectionBackground", TEXT, None),
    ("list inactive selection", "list.inactiveSelectionForeground", "list.inactiveSelectionBackground", TEXT, None),
    ("list hover text", "list.hoverForeground", "list.hoverBackground", TEXT, "foreground"),
    ("list highlight (filter match)", "list.highlightForeground", "quickInput.background", TEXT, None),
    ("input", "input.foreground", "input.background", TEXT, None),
    ("input placeholder", "input.placeholderForeground", "input.background", TEXT, None),
    ("dropdown", "dropdown.foreground", "dropdown.background", TEXT, None),
    ("editor widget", "editorWidget.foreground", "editorWidget.background", TEXT, None),
    ("suggest widget", "editorSuggestWidget.foreground", "editorSuggestWidget.background", TEXT, None),
    ("suggest widget selected", "editorSuggestWidget.foreground", "editorSuggestWidget.selectedBackground", TEXT, None),
    ("quick input", "quickInput.foreground", "quickInput.background", TEXT, None),
    ("notifications", "notifications.foreground", "notifications.background", TEXT, None),
    ("badge", "badge.foreground", "badge.background", TEXT, None),
    ("activity bar badge", "activityBarBadge.foreground", "activityBarBadge.background", TEXT, None),
    ("button", "button.foreground", "button.background", TEXT, None),
    ("status bar", "statusBar.foreground", "statusBar.background", TEXT, None),
    ("status bar debugging", "statusBar.debuggingForeground", "statusBar.debuggingBackground", TEXT, None),
    ("title bar active", "titleBar.activeForeground", "titleBar.activeBackground", TEXT, None),
    ("title bar inactive", "titleBar.inactiveForeground", "titleBar.inactiveBackground", TEXT, None),
    ("description text", "descriptionForeground", "editor.background", TEXT, None),
    ("line number", "editorLineNumber.foreground", "editor.background", TEXT, None),
    ("line number active", "editorLineNumber.activeForeground", "editor.background", TEXT, None),
    ("text link (editor)", "textLink.foreground", "editor.background", TEXT, None),
    ("text link (widget)", "textLink.foreground", "quickInput.background", TEXT, None),
    ("error text", "editorError.foreground", "editor.background", TEXT, None),
    ("warning text", "editorWarning.foreground", "editor.background", TEXT, None),
    ("info text", "editorInfo.foreground", "editor.background", TEXT, None),
    ("git added", "gitDecoration.addedResourceForeground", "sideBar.background", TEXT, None),
    ("git modified", "gitDecoration.modifiedResourceForeground", "sideBar.background", TEXT, None),
    ("git deleted", "gitDecoration.deletedResourceForeground", "sideBar.background", TEXT, None),
    ("terminal foreground", "terminal.foreground", "terminal.background", TEXT, None),
]

UI_PAIRS = [
    ("focus border", "focusBorder", "editor.background", UI),
    ("cursor", "editorCursor.foreground", "editor.background", UI),
    ("activity bar active border", "activityBar.activeBorder", "activityBar.background", UI),
    ("bracket match border", "editorBracketMatch.border", "editorBracketMatch.background", UI),
    ("indent guide active", "editorIndentGuide.activeBackground1", "editor.background", UI),
    ("scrollbar slider", "scrollbarSlider.background", "editor.background", UI),
    ("tab active border", "tab.activeBorderTop", "tab.activeBackground", UI),
    ("find match vs canvas", "editor.findMatchBackground", "editor.background", UI),
]

DECOR_PAIRS = [
    ("indent guide", "editorIndentGuide.background1", "editor.background", 1.0),
    ("whitespace dots", "editorWhitespace.foreground", "editor.background", 1.0),
    ("side bar border", "sideBar.border", "sideBar.background", 1.0),
    ("panel border", "panel.border", "panel.background", 1.0),
    ("tab border", "tab.border", "editorGroupHeader.tabsBackground", 1.0),
    ("widget border", "editorWidget.border", "editorWidget.background", 1.0),
]


def audit(name, path, verbose):
    with open(path, encoding="utf-8") as fh:
        theme = json.load(fh)
    c = theme["colors"]
    editor_bg = c["editor.background"]
    failures, warnings, stats = [], [], {"pass": 0, "skip": 0}
    measured = []

    def run(label, fg_value, bg_value, bar, kind):
        if fg_value is None or bg_value is None:
            stats["skip"] += 1
            return
        r = contrast(fg_value, bg_value, editor_bg)
        ok = r >= bar
        row = (r, label, fg_value, bg_value, bar)
        if kind == "fail":
            measured.append(row)
        if ok:
            stats["pass"] += 1
            if verbose:
                print(f"    {r:5.2f}  ok    {label:<32} {fg_value} on {bg_value}")
        elif kind == "warn":
            warnings.append(row)
        else:
            failures.append(row)

    for (label, fgk, bgk, bar, fb) in TEXT_PAIRS:
        fg = c.get(fgk, c.get(fb) if fb else None)
        run(label, fg, c.get(bgk), bar, "fail")

    for (label, fgk, bgk, bar) in UI_PAIRS:
        run(label, c.get(fgk), c.get(bgk), bar, "fail")

    for (label, fgk, bgk, bar) in DECOR_PAIRS:
        run(label, c.get(fgk), c.get(bgk), bar, "decor")
        if stats["pass"] and not verbose:
            pass

    for key, value in c.items():
        if not key.startswith("terminal.ansi"):
            continue
        if key in ANSI_SKIP:
            stats["skip"] += 1
            continue
        run(f"ansi {key.split('.')[-1]}", value, c.get("terminal.background"), TEXT, "fail")

    for entry in theme.get("tokenColors", []):
        scope = entry.get("scope")
        label = scope if isinstance(scope, str) else (scope or ["?"])[0]
        fg = entry.get("settings", {}).get("foreground")
        run(f"token {label}", fg, editor_bg, TEXT, "fail")
        run(f"token {label} @lineHighlight", fg, c.get("editor.lineHighlightBackground"), WARN, "warn")
        run(f"token {label} @selection", fg, c.get("editor.selectionBackground"), WARN, "warn")

    for token, fg in theme.get("semanticTokenColors", {}).items():
        if not isinstance(fg, str) or not fg.startswith("#"):
            continue
        run(f"semantic {token}", fg, editor_bg, TEXT, "fail")
        run(f"semantic {token} @selection", fg, c.get("editor.selectionBackground"), WARN, "warn")

    print(f"\n=== {name} ({theme['type']}) ===")
    if failures:
        print(f"  FAIL  {len(failures)} pair(s) below the bar:")
        for (r, label, fg, bg, bar) in sorted(failures):
            print(f"    {r:5.2f} < {bar:.1f}  {label:<34} {fg} on {bg}")
    else:
        print("  FAIL  none")
    if warnings:
        print(f"  WARN  {len(warnings)} pair(s) on a temporary highlight:")
        for (r, label, fg, bg, bar) in sorted(warnings)[:12]:
            print(f"    {r:5.2f} < {bar:.1f}  {label:<34} {fg} on {bg}")
        if len(warnings) > 12:
            print(f"    ... {len(warnings) - 12} more")
    print(f"  {stats['pass']} pair(s) pass, {stats['skip']} skipped")
    print("  tightest text/UI pairs (keep these above their bar when editing colors):")
    for (r, label, fg, bg, bar) in sorted(measured)[:6]:
        print(f"    {r:5.2f}  (bar {bar:.1f})  {label:<32} {fg} on {bg}")
    return len(failures)


def main():
    verbose = "-v" in sys.argv or "--all" in sys.argv
    bad = 0
    for name, path in THEMES:
        bad += audit(name, path, verbose)
    print()
    if bad:
        print(f"{bad} hard failure(s) - fix the colors above")
    else:
        print("All workbench text, token and terminal pairs meet WCAG AA.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
