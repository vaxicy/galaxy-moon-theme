# -*- coding: utf-8 -*-
"""Generate the README / Marketplace previews for Galaxy Moon Theme.

Builds a 1280x800 HTML mockup of the real VS Code workbench, driven by the actual
theme JSON files (workbench colors + tokenColors + semanticTokenColors), then
screenshots it with headless Chromium through Playwright.

Every color in the mockup comes from the theme JSON, so the previews always match
what the extension ships. After each shot the script samples a few pixels back and
compares them with the JSON, so a silently broken template is caught immediately.

Output: store-assets/screenshots/en/screenshot-light.png
        store-assets/screenshots/en/screenshot-dark.png

Usage:
    python3 scripts/generate-store-screenshots.py
"""

import json
import os
from urllib.parse import quote

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES = os.path.join(BASE, "themes")
OUT = os.path.join(BASE, "store-assets", "screenshots", "en")
TMP = os.path.join(BASE, "scripts", ".tmp-screenshot.html")

W, H = 1280, 800

ACTIVITY_ICONS = [
    # explorer
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<path d="M13 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V9z"/>'
    '<path d="M13 3v6h6"/></svg>',
    # search
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<circle cx="10.5" cy="10.5" r="5.5"/><path d="M15 15l5.5 5.5"/></svg>',
    # source control
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<circle cx="7" cy="5.5" r="2.3"/><circle cx="7" cy="18.5" r="2.3"/><circle cx="17.5" cy="10" r="2.3"/>'
    '<path d="M7 7.8v8.4"/><path d="M9.3 5.5h4.4a3.8 3.8 0 0 1 3.8 3.8v.4"/></svg>',
    # run and debug
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<path d="M7 4.5l12 7.5-12 7.5z"/></svg>',
    # extensions
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<rect x="4" y="4" width="6.6" height="6.6" rx="1.2"/><rect x="13.4" y="4" width="6.6" height="6.6" rx="1.2"/>'
    '<rect x="4" y="13.4" width="6.6" height="6.6" rx="1.2"/>'
    '<path d="M16.7 13.4v6.6M13.4 16.7h6.6"/></svg>',
]

BOTTOM_ICONS = [
    # account
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<circle cx="12" cy="8.5" r="3.6"/><path d="M4.8 20a7.4 7.4 0 0 1 14.4 0"/></svg>',
    # manage (gear)
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<circle cx="12" cy="12" r="3.4"/><circle cx="12" cy="12" r="7.6"/>'
    '<path d="M12 2.6v3M12 18.4v3M2.6 12h3M18.4 12h3"/></svg>',
]

# (text, token-class) per code line. The class maps to a tokenColors scope group.
CODE = [
    ("// Galaxy Moon Theme - the palette this theme is built from", "comment"),
    ('import { readFile } from "node:fs/promises";', "jsx"),
    ("", None),
    ("const NIGHT = '#222122';", "string"),
    ("const GOLD = '#E3CB54';", "string"),
    ("const PHASES = ['new', 'waxing crescent', 'full'];", "string"),
    ("", None),
    ("type Sky = {", "type"),
    ("  night: string;", "prop"),
    ("  gold: string;", "prop"),
    ("  stars: number;", "prop"),
    ("};", "type"),
    ("", None),
    ("export class Moon {", "type"),
    ("  private lit = 0.0;", "num"),
    ("", None),
    ("  /** Advance the moon one night, return how much of it is lit. */", "comment"),
    ("  rise(step = 0.125, drift = 0.02): number {", "func"),
    ("    const next = this.lit + step - drift;", "key"),
    ("    this.lit = Math.min(1, Math.round(next * 1000) / 1000);", "key"),
    ("    this.phase = PHASES[Math.floor(this.lit * PHASES.length)];", "key"),
    ("    return this.lit;", "key"),
    ("  }", "key"),
    ("", None),
    ("  async describe(file: string): Promise<Sky> {", "func"),
    ("    const source = await readFile(file, 'utf8');", "key"),
    ("    const stars = source.split('\\n').filter(isStar);", "key"),
    ("", None),
    ("    return { night: NIGHT, gold: GOLD, stars: stars.length };", "key"),
    ("  }", "key"),
    ("}", "type"),
    ("", None),
    ("const moon = new Moon();", "key"),
    ("console.log(await moon.describe('palette.json'));", "func"),
]

TOKEN_CLASSES = {
    "comment": ("comment",),
    "string": ("string", "string.template"),
    "key": ("keyword.control", "keyword", "storage.type"),
    "type": ("entity.name.type", "support.class", "entity.name.class"),
    "func": ("entity.name.function", "support.function", "entity.name.tag"),
    "prop": ("variable.other.property", "support.type.property-name", "variable"),
    "num": ("constant.numeric", "number"),
    "jsx": ("meta.import", "keyword.control", "keyword"),
}

TREE_ROWS = [
    (0, "folder", "galaxy-moon-theme", False),
    (1, "folder", "assets", False),
    (2, "file", "icon.png", False),
    (2, "folder", "logo-candidates", False),
    (1, "folder", "scripts", False),
    (2, "file", "generate-store-screenshots.py", False),
    (2, "file", "audit-contrast.py", False),
    (1, "folder", "themes", False),
    (2, "file", "dark-color-theme.json", True),
    (2, "file", "light-color-theme.json", False),
    (1, "file", "package.json", False),
    (1, "file", "README.md", False),
    (1, "file", "LICENSE", False),
]


# ---------------------------------------------------------------- helpers


def load_theme(filename):
    with open(os.path.join(THEMES, filename), encoding="utf-8") as fh:
        data = json.load(fh)

    colors = data.get("colors", {})
    tokens = {}
    for entry in data.get("tokenColors", []):
        scope = entry.get("scope")
        fg = (entry.get("settings") or {}).get("foreground")
        if not scope or not fg:
            continue
        scopes = scope if isinstance(scope, list) else scope.split(",")
        for item in scopes:
            tokens[item.strip()] = fg
    for name, value in data.get("semanticTokenColors", {}).items():
        fg = value if isinstance(value, str) else (value or {}).get("foreground")
        if fg:
            tokens.setdefault(name, fg)
    return colors, tokens


def rgb(colors, key, fallback):
    value = colors.get(key) or fallback
    return value


def token_color(tokens, classes, fallback):
    for name in classes:
        if name in tokens and tokens[name]:
            return tokens[name]
    for name in classes:
        for scope, color in tokens.items():
            if scope.startswith(name) and color:
                return color
    return fallback


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def current_line():
    """The line that gets the current-line highlight: the rise() signature."""
    for index, (text, _kind) in enumerate(CODE, start=1):
        if text.strip().startswith("rise("):
            return index
    return 1


def build_code_html(tokens, fallback_fg):
    rows = []
    active = current_line()
    for index, (text, kind) in enumerate(CODE, start=1):
        if not text:
            rows.append(
                f'<div class="ln"><span class="lnum">{index}</span>'
                f'<span class="ltxt">&nbsp;</span></div>'
            )
            continue
        color = token_color(tokens, TOKEN_CLASSES[kind], fallback_fg) if kind else fallback_fg
        cls = "ln current" if index == active else "ln"
        rows.append(
            f'<div class="{cls}"><span class="lnum">{index}</span>'
            f'<span class="ltxt" style="color:{color}">{esc(text)}</span></div>'
        )
    return "\n".join(rows)


def build_minimap():
    rows = []
    for text, _kind in CODE:
        width = min(64, max(6, len(text) * 1.9))
        rows.append(f'<div class="mm" style="width:{width:.0f}px"></div>')
    return "\n".join(rows)


HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html, body { width:__W__px; height:__H__px; overflow:hidden; }
  body { font-family:"Segoe UI", Arial, sans-serif; }
  .win { width:__W__px; height:__H__px; display:flex; flex-direction:column;
         background:__EDITOR_BG__; color:__EDITOR_FG__; }

  .titlebar { height:34px; flex:none; display:flex; align-items:center; position:relative;
              background:__TITLE_BG__; color:__TITLE_FG__; font-size:12.5px; }
  .titlebar .title { position:absolute; left:0; right:138px; text-align:center;
                     white-space:nowrap; overflow:hidden; }
  .titlebar .spacer { flex:1; }
  .winbtn { width:46px; height:34px; display:flex; align-items:center; justify-content:center; }
  .winbtn i { display:block; background:__TITLE_FG__; opacity:.72; }
  .winbtn.min i { width:11px; height:1px; }
  .winbtn.max i { width:9px; height:9px; border:1px solid __TITLE_FG__; background:none; }
  .winbtn.close i { width:11px; height:11px; background:none; position:relative; }
  .winbtn.close i::before, .winbtn.close i::after {
    content:""; position:absolute; left:0; top:5px; width:11px; height:1px;
    background:__TITLE_FG__; }
  .winbtn.close i::before { transform:rotate(45deg); }
  .winbtn.close i::after { transform:rotate(-45deg); }

  .body { flex:1; display:flex; min-height:0; }

  .activity { width:48px; flex:none; background:__ACT_BG__; display:flex;
              flex-direction:column; align-items:center; padding-top:8px; }
  .activity .act { width:48px; height:44px; display:flex; align-items:center;
                   justify-content:center; color:__ACT_INACTIVE__; }
  .activity .act svg { width:23px; height:23px; }
  .activity .act.on { color:__ACT_FG__; box-shadow:inset 2px 0 0 0 __ACT_BORDER__; }
  .activity .push { flex:1; }

  .side { width:240px; flex:none; background:__SIDE_BG__; color:__SIDE_FG__;
          border-right:1px solid __SIDE_BORDER__; font-size:12.5px; }
  .side .cap { height:34px; display:flex; align-items:center; justify-content:space-between;
               padding:0 14px; font-size:11px; letter-spacing:.08em; opacity:.82; }
  .tree { padding:2px 0 0 6px; }
  .row { display:flex; align-items:center; height:23px; padding-left:4px; font-size:12.5px;
         padding-right:10px; }
  .row .ico { width:15px; height:15px; margin-right:6px; flex:none; opacity:.9; }
  .row .ico svg { width:15px; height:15px; display:block; }
  .row .label { min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .row.muted { color:__SIDE_FG__; opacity:.78; }
  .row.sel { background:__SIDE_SEL_BG__; color:__SIDE_SEL_FG__; opacity:1; }

  .editor { flex:1; min-width:0; display:flex; flex-direction:column;
            background:__EDITOR_BG__; }
  .tabs { height:35px; flex:none; display:flex; background:__TABS_BG__; }
  .tab { height:35px; display:flex; align-items:center; padding:0 14px; font-size:13px;
         background:__TAB_INACTIVE_BG__; color:__TAB_INACTIVE_FG__; }
  .tab.on { background:__TAB_ACTIVE_BG__; color:__TAB_ACTIVE_FG__;
            box-shadow:inset 0 2px 0 0 __TAB_BORDER__; }
  .tab .dot { width:9px; height:9px; margin-right:8px; background:__TAB_BORDER__;
              transform:rotate(45deg); opacity:.9; }
  .tab.md .dot { background:__TAB_INACTIVE_FG__; transform:none; border-radius:2px; }
  .tab .x { margin-left:12px; width:11px; height:11px; position:relative; opacity:.6; }
  .tab .x::before, .tab .x::after { content:""; position:absolute; left:0; top:5px;
    width:11px; height:1px; background:currentColor; }
  .tab .x::before { transform:rotate(45deg); }
  .tab .x::after { transform:rotate(-45deg); }

  .crumbs { height:24px; flex:none; display:flex; align-items:center; gap:7px;
            padding:0 18px; font-size:12px; color:__CRUMB_FG__; }
  .crumbs .sep { opacity:.5; }

  .codewrap { flex:1; display:flex; min-height:0; }
  .code { flex:1; padding:8px 0 0 0; }
  .ln { display:flex; height:22px; align-items:center; }
  .ln.current { background:__LINE_HL__; }
  .lnum { width:52px; flex:none; text-align:right; padding-right:18px;
          font-family:Consolas,"Courier New",monospace; font-size:13px;
          color:__LINENO__; }
  .ltxt { font-family:Consolas,"Courier New",monospace; font-size:14px;
          white-space:pre; }
  .minimap { width:74px; flex:none; padding:10px 8px 0 8px; opacity:.55; }
  .minimap .mm { height:4px; margin-bottom:2px; border-radius:1px;
                 background:__EDITOR_FG__; opacity:.33; }

  .status { height:24px; flex:none; display:flex; align-items:center; gap:16px;
            padding:0 12px; background:__STATUS_BG__; color:__STATUS_FG__;
            font-size:12px; }
  .status .spacer { flex:1; }
  .status .item { display:flex; align-items:center; gap:6px; }
  .status svg { width:14px; height:14px; }
</style></head>
<body>
<div class="win">
  <div class="titlebar">
    <span class="title">__WINDOW_TITLE__</span>
    <span class="spacer"></span>
    <span class="winbtn min"><i></i></span>
    <span class="winbtn max"><i></i></span>
    <span class="winbtn close"><i></i></span>
  </div>
  <div class="body">
    <div class="activity">
      __ACTIVITY__
      <span class="push"></span>
      __BOTTOM_ACTIVITY__
    </div>
    <div class="side">
      <div class="cap"><span>EXPLORER</span><span>...</span></div>
      <div class="tree">
        __TREE__
      </div>
    </div>
    <div class="editor">
      <div class="tabs">
        <div class="tab on"><span class="dot"></span>index.ts<span class="x"></span></div>
        <div class="tab md"><span class="dot"></span>palette.json</div>
      </div>
      <div class="crumbs">
        <span>scripts</span><span class="sep">&gt;</span><span>demo</span>
        <span class="sep">&gt;</span><span>index.ts</span>
      </div>
      <div class="codewrap">
        <div class="code">
          __CODE__
        </div>
        <div class="minimap">
          __MINIMAP__
        </div>
      </div>
    </div>
  </div>
  <div class="status">
    <span class="item">__BRANCH__<span>master</span></span>
    <span class="item"><span>0</span><span>1</span></span>
    <span class="spacer"></span>
    <span class="item">Ln __LN__, Col 34</span>
    <span class="item">Spaces: 2</span>
    <span class="item">UTF-8</span>
    <span class="item">LF</span>
    <span class="item">TypeScript</span>
  </div>
</div>
</body></html>
"""

BRANCH_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">'
    '<circle cx="7" cy="5.5" r="2.2"/><circle cx="7" cy="18.5" r="2.2"/>'
    '<circle cx="17.5" cy="10" r="2.2"/><path d="M7 7.7v8.6"/>'
    '<path d="M9.2 5.5h4.3a4 4 0 0 1 4 4v.3"/></svg>'
)

FOLDER_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">'
    '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4l2 2.5h7A1.5 1.5 0 0 1 19 9v8.5A1.5 1.5 0 0 1 17.5 19h-13A1.5 1.5 0 0 1 3 17.5z"/></svg>'
)

FILE_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">'
    '<path d="M13 3H7a1.5 1.5 0 0 0-1.5 1.5v15A1.5 1.5 0 0 0 7 21h10a1.5 1.5 0 0 0 1.5-1.5V8.5z"/>'
    '<path d="M13 3v5.5h5.5"/></svg>'
)


def build_tree():
    rows = []
    for depth, kind, label, selected in TREE_ROWS:
        icon = FOLDER_SVG if kind == "folder" else FILE_SVG
        cls = "row sel" if selected else ("row muted" if depth else "row")
        rows.append(
            f'<div class="{cls}" style="padding-left:{4 + depth * 13}px">'
            f'<span class="ico">{icon}</span><span class="label">{label}</span></div>'
        )
    return "\n".join(rows)


def render_html(theme_file, title, window_title):
    colors, tokens = load_theme(theme_file)

    def c(key, fallback):
        return rgb(colors, key, fallback)

    editor_bg = c("editor.background", "#FFFFFF")
    editor_fg = c("editor.foreground", "#1F1F1F")
    side_bg = c("sideBar.background", editor_bg)
    side_fg = c("sideBar.foreground", editor_fg)

    activity = "\n".join(
        f'<span class="act{" on" if i == 0 else ""}">{svg}</span>'
        for i, svg in enumerate(ACTIVITY_ICONS)
    )
    bottom = "\n".join(f'<span class="act">{svg}</span>' for svg in BOTTOM_ICONS)
    line = current_line()

    replacements = {
        "__W__": str(W),
        "__H__": str(H),
        "__TITLE__": title,
        "__EDITOR_BG__": editor_bg,
        "__EDITOR_FG__": editor_fg,
        "__TITLE_BG__": c("titleBar.activeBackground", side_bg),
        "__TITLE_FG__": c("titleBar.activeForeground", side_fg),
        "__ACT_BG__": c("activityBar.background", side_bg),
        "__ACT_FG__": c("activityBar.foreground", side_fg),
        "__ACT_INACTIVE__": c("activityBar.inactiveForeground", side_fg),
        "__ACT_BORDER__": c("activityBar.activeBorder", c("focusBorder", side_fg)),
        "__SIDE_BG__": side_bg,
        "__SIDE_FG__": side_fg,
        "__SIDE_BORDER__": c("sideBar.border", side_bg),
        "__SIDE_SEL_BG__": c("list.activeSelectionBackground", side_bg),
        "__SIDE_SEL_FG__": c("list.activeSelectionForeground", side_fg),
        "__TABS_BG__": c("editorGroupHeader.tabsBackground", side_bg),
        "__TAB_ACTIVE_BG__": c("tab.activeBackground", editor_bg),
        "__TAB_ACTIVE_FG__": c("tab.activeForeground", editor_fg),
        "__TAB_INACTIVE_BG__": c("tab.inactiveBackground", side_bg),
        "__TAB_INACTIVE_FG__": c("tab.inactiveForeground", side_fg),
        "__TAB_BORDER__": c("tab.activeBorderTop", c("focusBorder", editor_fg)),
        "__CRUMB_FG__": c("descriptionForeground", editor_fg),
        "__LINE_HL__": c("editor.lineHighlightBackground", editor_bg),
        "__LINENO__": c("editorLineNumber.foreground", editor_fg),
        "__STATUS_BG__": c("statusBar.background", side_bg),
        "__STATUS_FG__": c("statusBar.foreground", side_fg),
        "__ACTIVITY__": activity,
        "__BOTTOM_ACTIVITY__": bottom,
        "__TREE__": build_tree(),
        "__CODE__": build_code_html(tokens, editor_fg),
        "__MINIMAP__": build_minimap(),
        "__BRANCH__": BRANCH_SVG,
        "__LN__": str(line),
        "__WINDOW_TITLE__": window_title,
    }

    html = HTML_TEMPLATE
    for key, value in replacements.items():
        html = html.replace(key, value)
    leftover = [key for key in replacements if key in html]
    assert not leftover, f"template placeholder left unfilled: {leftover}"
    return html


def pixel_qa(path, theme_file):
    """Sample flat areas of the shot and compare them with the theme JSON."""
    colors, _ = load_theme(theme_file)
    img = Image.open(path).convert("RGB")

    probes = [
        ("titleBar", (180, 12), "titleBar.activeBackground"),
        ("tabBar", (900, 50), "editorGroupHeader.tabsBackground"),
        ("activityBar", (24, 500), "activityBar.background"),
        ("sideBar", (130, 520), "sideBar.background"),
        ("editor", (1150, 520), "editor.background"),
        ("statusBar", (500, 794), "statusBar.background"),
    ]
    print("QA", os.path.basename(path))
    bad = 0
    for label, (x, y), key in probes:
        expected = colors.get(key)
        if not expected:
            print(f"  skip {label:12s} (no {key})")
            continue
        want = expected.lstrip("#")[:6].upper()
        got = "%02X%02X%02X" % img.getpixel((x, y))
        ok = got == want
        bad += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'DIFF'} {label:12s} {key:38s} expected #{want} got #{got}")
    return bad


def shoot(theme_file, out_name, title, window_title):
    html = render_html(theme_file, title, window_title)
    url = "file:///" + quote(TMP.replace("\\", "/"))
    with open(TMP, "w", encoding="utf-8") as fh:
        fh.write(html)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        page.goto(url)
        page.wait_for_timeout(450)
        path = os.path.join(OUT, out_name)
        page.screenshot(path=path)
        browser.close()
    print("saved", path)
    return pixel_qa(path, theme_file)


def main():
    os.makedirs(OUT, exist_ok=True)
    bad = 0
    bad += shoot(
        "galaxy-moon-theme-dark-color-theme.json",
        "screenshot-dark.png",
        "Galaxy Moon Theme Dark",
        "index.ts - galaxy-moon-demo - Visual Studio Code",
    )
    bad += shoot(
        "galaxy-moon-theme-light-color-theme.json",
        "screenshot-light.png",
        "Galaxy Moon Theme Light",
        "index.ts - galaxy-moon-demo - Visual Studio Code",
    )
    if os.path.exists(TMP):
        os.remove(TMP)
    print("pixel QA mismatches:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
