# -*- coding: utf-8 -*-
"""Capture real VS Code windows running the Galaxy Moon theme.

For every variant (light / dark) the script:
  1. builds an isolated VS Code profile (own --user-data-dir / --extensions-dir),
  2. installs this theme into that extension dir,
  3. writes settings.json that applies the variant and tags the window title,
  4. launches VS Code on scripts/demo-project,
  5. finds the window by title marker, resizes it and grabs it with PrintWindow
     (falling back to a screen grab when the GPU returns an empty frame),
  6. closes the window and cleans the temporary profile.

Output: store-assets/screenshots/en/screenshot-{light,dark}.png
Everything runs from Python with Unicode paths, so no shell encoding issues.

Usage:
    python3 scripts/capture-real-screenshots.py            # both variants
    python3 scripts/capture-real-screenshots.py light      # one variant
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageGrab

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_EXE = r"D:\安装\Microsoft VS Code\Code.exe"
DEMO_DIR = os.path.join(BASE, "scripts", "demo-project")
OUT_DIR = os.path.join(BASE, "store-assets", "screenshots", "en")
TMP_DIR = os.path.join(BASE, ".tmp")

WIDTH, HEIGHT = 1440, 900
# Windows still draws a 1px dark frame line inside the visible frame bounds;
# crop a few extra physical pixels so no dark outline survives the downscale.
EXTRA_CROP = 3
PUBLISHER = "lilinhuang"
NAME = "galaxy-moon-theme"
VERSION = "1.0.0"
WORK_NAME = "galaxy-moon-demo"   # demo folder name doubles as the window marker

VARIANTS = [
    ("light", "Galaxy Moon Theme Light"),
    ("dark", "Galaxy Moon Theme Dark"),
]

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

DWMWA_EXTENDED_FRAME_BOUNDS = 9

SW_RESTORE = 9
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
PW_RENDERFULLCONTENT = 0x00000002
BI_RGB = 0
WM_CLOSE = 0x0010

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


def declare_signatures():
    """64-bit safe signatures - plain ints would truncate HWND/HDC."""
    user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
    user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.GetWindowRect.restype = ctypes.c_bool
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetForegroundWindow.argtypes = [wt.HWND]
    user32.GetWindowDC.argtypes = [wt.HWND]
    user32.GetWindowDC.restype = wt.HDC
    user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, ctypes.c_uint]
    user32.PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
    user32.GetDpiForWindow.argtypes = [wt.HWND]
    user32.GetDpiForWindow.restype = ctypes.c_uint
    gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
    gdi32.CreateCompatibleDC.restype = wt.HDC
    gdi32.CreateCompatibleBitmap.argtypes = [wt.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.CreateCompatibleBitmap.restype = wt.HBITMAP
    gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    gdi32.SelectObject.restype = wt.HGDIOBJ
    gdi32.GetDIBits.argtypes = [wt.HDC, wt.HBITMAP, ctypes.c_uint, ctypes.c_uint,
                                ctypes.c_void_p, ctypes.POINTER(BITMAPINFO),
                                ctypes.c_uint]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wt.HDC]
    dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p,
                                             wt.DWORD]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


def make_dpi_aware():
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def window_text(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_rect(hwnd):
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def find_windows(marker):
    found = []

    def callback(hwnd, _):
        title = window_text(hwnd)
        if title and marker.lower() in title.lower() and "Visual Studio Code" in title:
            _, _, w, h = window_rect(hwnd)
            found.append((w * h, hwnd, title))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    found.sort(reverse=True)
    return found


def wait_for_window(marker, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        matches = find_windows(marker)
        if matches:
            return matches[0]
        time.sleep(1.0)
    return None


def resize_window(hwnd, width, height):
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, None, 0, 0, int(width), int(height),
                        SWP_NOZORDER | SWP_NOACTIVATE)


def frame_insets(hwnd):
    """Thickness of the invisible resize frame DWM paints as #202020.

    GetWindowRect includes that frame; DWMWA_EXTENDED_FRAME_BOUNDS excludes it,
    so the difference tells us how many pixels to crop off each side.
    """
    win = wt.RECT()
    frame = wt.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(win)):
        return (0, 0, 0, 0)
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                      ctypes.byref(frame), ctypes.sizeof(frame))
    if hr != 0:
        return (0, 0, 0, 0)
    return (max(0, frame.left - win.left), max(0, frame.top - win.top),
            max(0, win.right - frame.right), max(0, win.bottom - frame.bottom))


def print_window(hwnd):
    _, _, w, h = window_rect(hwnd)
    hdc = user32.GetWindowDC(hwnd)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(memdc, bitmap)
    try:
        user32.PrintWindow(hwnd, memdc, PW_RENDERFULLCONTENT)
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = w
        info.bmiHeader.biHeight = -h
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(memdc, bitmap, 0, h, buf, ctypes.byref(info), 0)
        return Image.frombytes("RGB", (w, h), bytes(buf), "raw", "BGRX", 0, 1)
    finally:
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(hwnd, hdc)


def screen_grab(hwnd):
    user32.SetForegroundWindow(hwnd)
    time.sleep(1.6)
    left, top, w, h = window_rect(hwnd)
    return ImageGrab.grab(bbox=(left, top, left + w, top + h), all_screens=True)


def looks_empty(img):
    small = img.convert("L").resize((40, 25))
    pixels = list(small.getdata())
    mean = sum(pixels) / len(pixels)
    var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
    return mean < 12 and var < 40


SETTINGS = {
    "window.title": "${activeEditorShort}${separator}${rootName}${separator}${appName}",
    "workbench.colorTheme": "{theme}",
    "workbench.startupEditor": "none",
    "workbench.tips.enabled": False,
    "workbench.welcomePage.walkthroughs.openOnInstall": False,
    "workbench.editor.empty.hint": "hidden",
    "workbench.activityBar.location": "default",
    "workbench.secondarySideBar.defaultVisibility": "hidden",
    "chat.disableAIFeatures": True,
    "chat.commandCenter.enabled": False,
    "workbench.statusBar.visible": True,
    "breadcrumbs.enabled": True,
    "update.showReleaseNotes": False,
    "update.mode": "none",
    "telemetry.telemetryLevel": "off",
    "security.workspace.trust.enabled": False,
    "extensions.autoUpdate": False,
    "extensions.ignoreRecommendations": True,
    "explorer.compactFolders": False,
    "explorer.confirmDragAndDrop": False,
    "editor.fontFamily": "Consolas, 'Courier New', monospace",
    "editor.fontSize": 14,
    "editor.lineHeight": 22,
    "editor.minimap.enabled": True,
    "editor.renderWhitespace": "none",
    "editor.cursorBlinking": "solid",
    "editor.bracketPairColorization.enabled": False,
    "editor.guides.indentation": True,
    "editor.scrollBeyondLastLine": False,
    "git.enabled": False,
    "git.decorations.enabled": False,
    "files.autoSave": "off",
    "window.menuBarVisibility": "classic",
    "window.commandCenter": False,
}


def close_windows(needle):
    """Ask every top level window whose title contains `needle` to close."""
    closed = 0

    def callback(hwnd, _):
        nonlocal closed
        title = window_text(hwnd)
        if title and needle.lower() in title.lower():
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            closed += 1
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return closed


def prepare_profile(variant, theme_label):
    user_dir = os.path.join(TMP_DIR, f"{variant}-user")
    ext_dir = os.path.join(TMP_DIR, f"{variant}-ext")
    work_dir = os.path.join(TMP_DIR, WORK_NAME)
    shutil.rmtree(user_dir, ignore_errors=True)
    shutil.rmtree(ext_dir, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    os.makedirs(user_dir, exist_ok=True)
    shutil.copytree(DEMO_DIR, work_dir)

    ext_root = os.path.join(ext_dir, f"{PUBLISHER}.{NAME}-{VERSION}")
    os.makedirs(ext_root, exist_ok=True)
    shutil.copy(os.path.join(BASE, "package.json"),
                os.path.join(ext_root, "package.json"))
    shutil.copytree(os.path.join(BASE, "themes"), os.path.join(ext_root, "themes"))

    settings = {k: (v.replace("{theme}", theme_label) if isinstance(v, str) else v)
                for k, v in SETTINGS.items()}
    settings_dir = os.path.join(user_dir, "User")
    os.makedirs(settings_dir, exist_ok=True)
    with open(os.path.join(settings_dir, "settings.json"), "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2, ensure_ascii=False)
    return user_dir, ext_dir, work_dir


def capture(variant, theme_label, marker):
    close_windows(marker)
    time.sleep(1.0)
    user_dir, ext_dir, work_dir = prepare_profile(variant, theme_label)
    demo_file = os.path.join(work_dir, "index.js")
    argv = [
        CODE_EXE,
        "--user-data-dir", user_dir,
        "--extensions-dir", ext_dir,
        "--new-window",
        "--skip-welcome",
        "--skip-release-notes",
        "--disable-workspace-trust",
        "--disable-gpu-sandbox",
        work_dir, demo_file,
    ]
    print(f"[{variant}] launching VS Code with {theme_label}")
    subprocess.Popen(argv, cwd=BASE, close_fds=True)

    match = wait_for_window(marker, timeout=120)
    if not match:
        print(f"[{variant}] window with marker {marker!r} not found", file=sys.stderr)
        return False
    _, hwnd, title = match
    print(f"[{variant}] window: {title!r}")

    scale = (user32.GetDpiForWindow(hwnd) or 96) / 96.0
    insets = frame_insets(hwnd)
    print(f"[{variant}] dpi {scale:.2f}, frame insets {insets}")
    # size the window so that the *visible* frame is exactly WIDTH x HEIGHT logical
    resize_window(hwnd, WIDTH * scale + insets[0] + insets[2],
                  HEIGHT * scale + insets[1] + insets[3])
    time.sleep(4.0)

    img = print_window(hwnd)
    print(f"[{variant}] printwindow {img.size}")
    if looks_empty(img):
        print(f"[{variant}] empty frame, falling back to screen grab")
        img = screen_grab(hwnd)
    if any(insets):
        left, top, right, bottom = insets
        img = img.crop((left, top, img.width - right, img.height - bottom))
        print(f"[{variant}] cropped the invisible frame -> {img.size}")
    if EXTRA_CROP:
        img = img.crop((EXTRA_CROP, EXTRA_CROP,
                        img.width - EXTRA_CROP, img.height - EXTRA_CROP))
        print(f"[{variant}] cropped the 1px OS frame line -> {img.size}")
    if img.size != (WIDTH, HEIGHT):
        img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"screenshot-{variant}.png")
    img.save(out)
    print(f"[{variant}] saved {out} {img.size} (dpi {scale:.2f})")

    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    time.sleep(3.0)
    return True


def main():
    wanted = sys.argv[1:] or [v[0] for v in VARIANTS]
    if not os.path.exists(CODE_EXE):
        print(f"VS Code not found at {CODE_EXE}", file=sys.stderr)
        return 1
    declare_signatures()
    make_dpi_aware()
    os.makedirs(TMP_DIR, exist_ok=True)
    if close_windows(WORK_NAME):
        print("closed window(s) left over from an earlier run")
    time.sleep(1.0)
    ok = True
    for variant, theme_label in VARIANTS:
        if variant not in wanted:
            continue
        ok = capture(variant, theme_label, WORK_NAME) and ok
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
