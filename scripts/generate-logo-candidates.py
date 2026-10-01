# -*- coding: utf-8 -*-
"""Galaxy Moon Theme —— logo 候选方案生成器（PIL 纯代码绘制）

产出 assets/logo-candidates/：
  0N-<slug>.png          每个方案 512px 主图（透明底）
  0N-<slug>-256.png      256px 预览
  0N-<slug>-128.png      128px 预览
  contact-dark.png       6 宫格总览（深色底）+ 64/32/16px 可读性条
  contact-light.png      同一总览的浅色底版本（检查浅底可读性）

同时把定稿方案（01 Crescent & Stars）裁边铺满画布，输出扩展图标 assets/icon.png
（透明底、无外框，与同类主题项目的 icon.png 约定一致）。

实现要点：
  * 所有绘制在 2048 画布完成（SS=4 超采样），最后 LANCZOS 降采样 → 抗锯齿边缘。
  * 全程相对路径 + cwd=项目根，规避 Windows 中文路径下 PIL save 间歇 OSError 22。
  * 每个方案生成后自动断言：不触画布边缘、视觉内容不超出 8px 安全边距。
用法（必须从项目根目录、用 python3 执行）：
    python3 scripts/generate-logo-candidates.py
"""

import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
OUT = "assets/logo-candidates"
ICON_PATH = "assets/icon.png"
ICON_FILL = 0.94                        # 图标主体占画布比例（与同类项目 icon.png 观感一致）
ICON_SRC = 0                            # 定稿方案下标 → 01 Crescent & Stars

SS = 4                                  # 超采样倍数
BASE = 512                              # 逻辑画布尺寸
W = BASE * SS                           # 实际绘制尺寸 2048
CEN = BASE / 2.0

# ---------- 主题色板（取自 themes/galaxy-moon-theme-dark-color-theme.json） ----------
NIGHT = (0x22, 0x21, 0x22, 255)
NIGHT_2 = (0x33, 0x33, 0x33, 255)
NIGHT_3 = (0x3B, 0x3B, 0x3B, 255)
GOLD = (0xE3, 0xCB, 0x54, 255)
GOLD_LIGHT = (0xF7, 0xE9, 0xA2, 255)
GOLD_DEEP = (0xBE, 0xA2, 0x2E, 255)
LAVENDER = (0xF1, 0xE9, 0xF1, 255)
PINK = (0xB9, 0x79, 0x95, 255)
TEAL = (0x6D, 0xA2, 0xA8, 255)
GREY = (0x9A, 0x95, 0x9A, 255)
PLUM = (0x6F, 0x46, 0x6F, 255)
INK = (0x0F, 0x0E, 0x10, 255)


# ============================== 通用工具 ==============================
def mix(c0, c1, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(c0[i] + (c1[i] - c0[i]) * t)) for i in range(len(c0)))


def px(v):
    return int(round(v * SS))


def new():
    return Image.new("RGBA", (W, W), (0, 0, 0, 0))


def circle_mask(cx, cy, r):
    m = Image.new("L", (W, W), 0)
    ImageDraw.Draw(m).ellipse([px(cx - r), px(cy - r), px(cx + r), px(cy + r)], fill=255)
    return m


def ring_mask(cx, cy, r_out, r_in):
    return ImageChops.subtract(circle_mask(cx, cy, r_out), circle_mask(cx, cy, r_in))


def crescent_mask(cx, cy, r_out, r_in, off):
    return ImageChops.subtract(circle_mask(cx, cy, r_out), circle_mask(cx + off[0], cy + off[1], r_in))


def rrect_mask(x0, y0, x1, y1, rad):
    m = Image.new("L", (W, W), 0)
    ImageDraw.Draw(m).rounded_rectangle([px(x0), px(y0), px(x1), px(y1)], radius=px(rad), fill=255)
    return m


def sparkle_mask(cx, cy, r, waist=0.30):
    """四角星（8 顶点交替半径）。"""
    m = Image.new("L", (W, W), 0)
    pts = []
    for k in range(8):
        ang = -math.pi / 2 + k * math.pi / 4
        rr = r if k % 2 == 0 else r * waist
        pts.append((px(cx + rr * math.cos(ang)), px(cy + rr * math.sin(ang))))
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m.filter(ImageFilter.GaussianBlur(px(1.2)))


def lgrad(c0, c1, angle=90.0):
    """线性渐变（angle=90 → 自上而下），返回覆盖整个逻辑画布的 RGBA 图。"""
    n = int(W * 1.5)
    g = Image.new("RGBA", (n, n))
    d = ImageDraw.Draw(g)
    for y in range(n):
        d.line([(0, y), (n, y)], fill=mix(c0, c1, y / (n - 1)))
    g = g.rotate(angle, resample=Image.BICUBIC, expand=False)
    off = (n - W) // 2
    return g.crop((off, off, off + W, off + W))


def radial_rgb(c0, c1, r, center=(CEN, CEN), steps=150):
    """中心 c0 → 半径 r 处 c1 的径向渐变。"""
    img = Image.new("RGBA", (W, W), c1)
    d = ImageDraw.Draw(img)
    cx, cy = px(center[0]), px(center[1])
    R = px(r)
    for i in range(steps, -1, -1):
        t = i / steps
        rr = R * t
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=mix(c0, c1, t))
    return img


def glow(size, color, center, r, max_a=120, power=2.4, steps=150):
    """柔和径向光晕（半径 r 单位为像素，与传入 size 同一坐标系）。"""
    img = Image.new("RGBA", size, tuple(color[:3]) + (0,))
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for i in range(steps, -1, -1):
        t = i / steps
        a = int(max_a * max(0.0, (1.0 - t) ** power))
        rr = max(0.5, r * t)
        d.ellipse([center[0] - rr, center[1] - rr, center[0] + rr, center[1] + rr], fill=a)
    img.putalpha(m)
    return img


def mark_glow(color, r, max_a, power=2.4, center=(CEN, CEN)):
    return glow((W, W), color, (px(center[0]), px(center[1])), px(r), max_a=max_a, power=power)


def layer_from(mask, fill, alpha=255):
    """按 mask 裁出图层。fill 可为颜色元组或整幅 RGBA 图。"""
    out = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    src = fill if isinstance(fill, Image.Image) else Image.new("RGBA", (W, W), tuple(fill[:3]) + (255,))
    m = mask if alpha >= 255 else mask.point(lambda v: int(v * alpha / 255))
    out.paste(src, (0, 0), m)
    return out


def rim(body, dx, dy):
    """取实心图形左上侧的一圈亮边。"""
    return ImageChops.subtract(body, ImageChops.offset(body, px(dx), px(dy)))


def check(img, name):
    """边缘零透明 + 视觉内容不越安全边距。"""
    a = img.getchannel("A")
    for x in range(0, W, 16):
        assert a.getpixel((x, 0)) == 0 and a.getpixel((x, W - 1)) == 0, f"{name}: 内容触到画布上下边缘"
    for y in range(0, W, 16):
        assert a.getpixel((0, y)) == 0 and a.getpixel((W - 1, y)) == 0, f"{name}: 内容触到画布左右边缘"
    bbox = a.point(lambda v: 255 if v > 8 else 0).getbbox()
    assert bbox, f"{name}: 内容为空"
    x0, y0, x1, y1 = (v / SS for v in bbox)
    assert x0 >= 8 and y0 >= 8 and x1 <= BASE - 8 and y1 <= BASE - 8, (
        f"{name}: 视觉内容超出安全边距 bbox=({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})")
    return (x0, y0, x1, y1)


# ============================== 6 个方案 ==============================
def c1_crescent_stars():
    """01 新月 + 星：最直白的月亮联想，辨识度最高。"""
    img = new()
    cx, cy, R, r, off = 244, 254, 170, 182, (74, -44)
    img.alpha_composite(mark_glow(GOLD, 236, 78, power=2.8, center=(cx, cy)))
    body = crescent_mask(cx, cy, R, r, off)
    img.alpha_composite(layer_from(body, lgrad(GOLD_LIGHT, GOLD_DEEP, angle=-42)))
    img.alpha_composite(layer_from(rim(body, 10, 8), GOLD_LIGHT, alpha=205))
    for (sx, sy, sr) in ((368, 148, 33), (432, 246, 21), (374, 336, 15)):
        img.alpha_composite(layer_from(sparkle_mask(sx, sy, sr), LAVENDER))
    for (sx, sy, sr) in ((468, 152, 9), (300, 92, 8)):
        img.alpha_composite(layer_from(circle_mask(sx, sy, sr), LAVENDER, alpha=210))
    return img


def c2_eclipse():
    """02 Eclipse：金色日冕环 + 暗月盘，几何感强。"""
    img = new()
    img.alpha_composite(mark_glow(GOLD, 250, 118, power=3.2))
    img.alpha_composite(layer_from(circle_mask(CEN, CEN, 152), radial_rgb((0x3E, 0x3A, 0x3F, 255), INK, 152)))
    img.alpha_composite(layer_from(ring_mask(CEN, CEN, 154, 149), LAVENDER, alpha=110))
    img.alpha_composite(layer_from(ring_mask(CEN, CEN, 196, 152), radial_rgb(LAVENDER, GOLD, 196)))
    img.alpha_composite(layer_from(ring_mask(CEN, CEN, 170, 152), GOLD_LIGHT, alpha=90))
    sx = CEN + 204 * math.cos(math.radians(-56))
    sy = CEN + 204 * math.sin(math.radians(-56))
    img.alpha_composite(mark_glow(GOLD_LIGHT, 44, 120, power=2.0, center=(sx, sy)))
    img.alpha_composite(layer_from(sparkle_mask(sx, sy, 25), GOLD_LIGHT, alpha=240))
    return img


def c3_orbit():
    """03 Orbit：细金环 + 月牙 + 环绕点，轻科技感。"""
    img = new()
    img.alpha_composite(mark_glow(GOLD, 244, 60, power=2.6))
    img.alpha_composite(layer_from(ring_mask(CEN, CEN, 178, 164), lgrad(GOLD_DEEP, GOLD_LIGHT, angle=24)))
    cx, cy = 236, 252
    body = crescent_mask(cx, cy, 116, 126, (50, -30))
    img.alpha_composite(layer_from(body, lgrad(GOLD_LIGHT, GOLD_DEEP, angle=-40)))
    img.alpha_composite(layer_from(rim(body, 8, 6), GOLD_LIGHT, alpha=200))
    ax = CEN + 171 * math.cos(math.radians(-42))
    ay = CEN + 171 * math.sin(math.radians(-42))
    img.alpha_composite(mark_glow(TEAL, 46, 150, power=2.0, center=(ax, ay)))
    img.alpha_composite(layer_from(circle_mask(ax, ay, 19), TEAL))
    img.alpha_composite(layer_from(circle_mask(CEN - 148, CEN + 85, 11), LAVENDER, alpha=225))
    return img


ARM_TILT = math.radians(-24)        # 星系盘整体倾斜角
ARM_SQUASH = 0.74                   # 盘面透视压扁系数


def spiral_arm(c0, c1, turns, phase=0.0, r0=46.0, r1=186.0, w0=32.0, w1=8.0,
               alpha=245, halo_scale=1.7, halo_alpha=95):
    """沿阿基米德螺线生成一条锥形旋臂多边形带（掩码 + 径向渐变上色）。

    注意：ImageDraw 在 RGBA 上是覆盖而非叠加，逐点盖圆会互相冲掉；这里改为
    先算带宽轮廓 → 多边形掩码 → （模糊掩码后再上色，避免颜色通道出现黑边）。
    """
    ca, sa = math.cos(ARM_TILT), math.sin(ARM_TILT)
    steps = 64

    def pos(tt):
        a = phase + tt * turns * 2 * math.pi
        rr = r0 + (r1 - r0) * tt
        u = rr * math.cos(a)
        v = rr * math.sin(a) * ARM_SQUASH
        return (CEN + u * ca - v * sa, CEN + u * sa + v * ca)

    pts = [pos(i / steps) for i in range(steps + 1)]
    nrm = []
    for i in range(len(pts)):
        j, k = min(i + 1, len(pts) - 1), max(i - 1, 0)
        dx = pts[j][0] - pts[k][0]
        dy = pts[j][1] - pts[k][1]
        ln = math.hypot(dx, dy) or 1.0
        nrm.append((-dy / ln, dx / ln))

    def band(scale, a, blur):
        left, right = [], []
        for i, (x, y) in enumerate(pts):
            t = i / (len(pts) - 1)
            w = (w0 + (w1 - w0) * t) * scale
            nx, ny = nrm[i]
            left.append((px(x + nx * w / 2), px(y + ny * w / 2)))
            right.append((px(x - nx * w / 2), px(y - ny * w / 2)))
        m = Image.new("L", (W, W), 0)
        ImageDraw.Draw(m).polygon(left + right[::-1], fill=255)
        m = m.filter(ImageFilter.GaussianBlur(px(blur)))
        return layer_from(m, radial_rgb(c0, c1, r1), alpha)

    arm = band(halo_scale, halo_alpha, 9.0)
    arm.alpha_composite(band(1.0, alpha, 2.2))
    return arm


def c4_galaxy():
    """04 Galaxy Spiral：双旋臂星系 + 月核，最贴合主题名。"""
    img = new()
    img.alpha_composite(mark_glow(PLUM, 236, 56, power=2.6))
    arms = spiral_arm(LAVENDER, GOLD, 1.2, phase=-0.35)
    arms.alpha_composite(spiral_arm(LAVENDER, PINK, 1.2, phase=-0.35 + math.pi))
    img.alpha_composite(arms)
    img.alpha_composite(mark_glow(LAVENDER, 58, 148, power=2.4))
    img.alpha_composite(mark_glow(GOLD, 30, 120, power=2.0))
    core = crescent_mask(CEN - 3, CEN - 5, 42, 45, (16, -10))
    img.alpha_composite(layer_from(core, GOLD_LIGHT))
    for (ang, rr) in ((-2.35, 196), (-1.55, 224), (-0.62, 206), (0.35, 226), (1.85, 214)):
        x = CEN + rr * math.cos(ang)
        y = CEN + rr * math.sin(ang) * ARM_SQUASH
        img.alpha_composite(layer_from(circle_mask(x, y, 6), LAVENDER, alpha=165))
    return img


def c5_pixel_moon():
    """05 Pixel Moon：11x11 像素格里的月牙 + 两颗像素星，复古开发者味。"""
    img = new()
    img.alpha_composite(mark_glow(GOLD, 230, 62, power=2.8))
    n, cell = 11, 32.0
    ox = CEN - n * cell / 2.0
    oy = CEN - n * cell / 2.0
    R, r, off = 150.0, 134.0, (58.0, -38.0)
    span = n * cell
    cells = []
    for j in range(n):
        for i in range(n):
            x = (i + 0.5) * cell - span / 2.0
            y = (j + 0.5) * cell - span / 2.0
            inside = (x * x + y * y) <= R * R and ((x - off[0]) ** 2 + (y - off[1]) ** 2) > r * r
            if inside:
                cells.append((i, j, y))
    assert cells, "05 Pixel Moon: 像素月牙为空"
    occupied = {(i, j) for (i, j, _y) in cells}
    for (i, j, y) in cells:
        col = mix(GOLD_LIGHT, GOLD_DEEP, (y + span / 2.0) / span)
        x0 = ox + i * cell
        y0 = oy + j * cell
        img.alpha_composite(layer_from(rrect_mask(x0 + 1.5, y0 + 1.5, x0 + cell - 1.5, y0 + cell - 1.5, 6), col))
    for (si, sj) in ((9, 1), (9, 5)):
        for (di, dj) in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            i, j = si + di, sj + dj
            assert (i, j) not in occupied, f"05 Pixel Moon: 像素星与月牙重叠 {(i, j)}"
            x0 = ox + i * cell
            y0 = oy + j * cell
            img.alpha_composite(layer_from(rrect_mask(x0 + 3, y0 + 3, x0 + cell - 3, y0 + cell - 3, 4), LAVENDER))
    return img


def c6_moonrise():
    """06 Moonrise：月牙升起在三条代码行（语法色）之上。"""
    img = new()
    img.alpha_composite(mark_glow(GOLD, 220, 72, power=2.8, center=(256, 208)))
    body = crescent_mask(256, 208, 126, 140, (62, -34))
    img.alpha_composite(layer_from(body, lgrad(GOLD_LIGHT, GOLD_DEEP, angle=-40)))
    img.alpha_composite(layer_from(rim(body, 8, 7), GOLD_LIGHT, alpha=200))
    img.alpha_composite(layer_from(sparkle_mask(110, 96, 20), LAVENDER))
    img.alpha_composite(layer_from(circle_mask(408, 128, 9), LAVENDER, alpha=210))
    for (x0, y0, w, col) in ((112, 352, 300, TEAL), (112, 396, 228, PINK), (112, 440, 164, GREY)):
        img.alpha_composite(layer_from(rrect_mask(x0, y0, x0 + w, y0 + 26, 13), col))
    return img


CONCEPTS = [
    ("01", "crescent-stars", "Crescent & Stars", "Chunky gold crescent + lavender sparkles.", c1_crescent_stars),
    ("02", "eclipse", "Eclipse", "Gold corona ring around a dark moon disc.", c2_eclipse),
    ("03", "orbit", "Orbit", "Thin gold ring, crescent moon, orbiting dot.", c3_orbit),
    ("04", "galaxy-spiral", "Galaxy Spiral", "Two soft spiral arms with a moon-lit core.", c4_galaxy),
    ("05", "pixel-moon", "Pixel Moon", "Retro pixel crescent + pixel stars.", c5_pixel_moon),
    ("06", "moonrise", "Moonrise", "Crescent rising over three code bars.", c6_moonrise),
]


# ============================== 总览图 ==============================
SHEET_MODES = {
    "dark": {
        "path": "contact-dark.png",
        "bg": (0x16, 0x15, 0x16, 255),
        "ink": LAVENDER,
        "head": GOLD,
        "sub": GREY,
        "rule": (0x3D, 0x3C, 0x3D, 255),
        "tiny": (0x77, 0x72, 0x77, 255),
        "glow": (34, 26),
    },
    "light": {
        "path": "contact-light.png",
        "bg": (0xF6, 0xF5, 0xF6, 255),
        "ink": (0x23, 0x22, 0x23, 255),
        "head": (0x8E, 0x74, 0x0E, 255),
        "sub": (0x6E, 0x6A, 0x6E, 255),
        "rule": (0xD8, 0xD5, 0xD8, 255),
        "tiny": (0x8A, 0x86, 0x8A, 255),
        "glow": (40, 30),
    },
}


def font(size, bold=False):
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    path = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", name)
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def build_sheet(marks, mode):
    pal = SHEET_MODES[mode]
    SW, SH = 1600, 1300
    M = 60
    RIGHT = SW - M
    GX = 40
    COL_W = (RIGHT - M - 2 * GX) // 3
    COL_X = [M + i * (COL_W + GX) for i in range(3)]
    assert COL_X[2] + COL_W <= RIGHT, "总览图：最后一列右缘越界"
    ROW_Y = [176, 706]
    MARK = 300
    SIZES = (64, 32, 16)

    sheet = Image.new("RGBA", (SW, SH), pal["bg"])
    sheet.alpha_composite(glow((SW, SH), GOLD, (300, 120), 620, max_a=pal["glow"][0], power=2.2))
    sheet.alpha_composite(glow((SW, SH), TEAL, (1420, 1080), 560, max_a=pal["glow"][1], power=2.2))

    d = ImageDraw.Draw(sheet)
    d.text((M, 64), "Galaxy Moon Theme - Logo Candidates", font=font(44, True), fill=pal["ink"])
    d.text((M, 122), f"{len(CONCEPTS)} concepts · palette from theme JSON (#222122 / #E3CB54 / #F1E9F1)", font=font(20), fill=pal["sub"])
    d.line([(M, 158), (RIGHT, 158)], fill=pal["rule"], width=2)

    for idx, (num, _slug, title, caption, _fn) in enumerate(CONCEPTS):
        col, row = idx % 3, idx // 3
        x, y = COL_X[col], ROW_Y[row]
        assert x + COL_W <= RIGHT
        mark = marks[idx].resize((MARK, MARK), Image.LANCZOS)
        sheet.alpha_composite(mark, (x + (COL_W - MARK) // 2, y))
        d.text((x, y + MARK + 26), f"{num}  {title}", font=font(28, True), fill=pal["head"])
        d.text((x, y + MARK + 62), caption, font=font(19), fill=pal["sub"])
        sy = y + MARK + 108
        cx = x
        for s in SIZES:
            small = marks[idx].resize((s, s), Image.LANCZOS)
            sheet.alpha_composite(small, (cx, sy + (64 - s)))
            d.text((cx, sy + 70), f"{s}px", font=font(14), fill=pal["tiny"])
            cx += s + 22
        assert sy + 64 <= SH - 12, "总览图：可读性条越出画布"
        if row == 0:
            assert sy + 64 < ROW_Y[1], "总览图：第一行与第二行重叠"

    d.text((M, SH - 66), "Readability strip 64 / 32 / 16 px  ·  every mark is transparent-background, 512 px master + 128 px preview",
           font=font(19), fill=pal["tiny"])
    return sheet.convert("RGB")


def build_icon(mark):
    """定稿方案 → assets/icon.png：按视觉外框裁边、等比铺满画布、居中（透明底、无外框）。"""
    a = mark.getchannel("A").point(lambda v: 255 if v > 40 else 0)
    box = a.getbbox()
    assert box, "icon: 定稿方案为空"
    cropped = mark.crop(box)
    scale = ICON_FILL * BASE / max(cropped.size)
    size = (max(1, int(round(cropped.width * scale))), max(1, int(round(cropped.height * scale))))
    assert size[0] <= BASE and size[1] <= BASE, "icon: 主体超出画布"
    icon = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    icon.alpha_composite(cropped.resize(size, Image.LANCZOS),
                         ((BASE - size[0]) // 2, (BASE - size[1]) // 2))
    corners = [icon.getpixel(p)[3] for p in ((0, 0), (BASE - 1, 0), (0, BASE - 1), (BASE - 1, BASE - 1))]
    assert corners == [0, 0, 0, 0], f"icon: 四角必须透明，实际 {corners}"
    print(f"  icon                   {size[0]}x{size[1]} in {BASE}x{BASE}")
    return icon


def main():
    os.makedirs(OUT, exist_ok=True)
    marks = []
    for (num, slug, _title, _caption, fn) in CONCEPTS:
        img = fn()
        tag = f"{num} {slug}"
        bbox = check(img, tag)
        print(f"  {tag:<22} bbox=({bbox[0]:.0f},{bbox[1]:.0f})-({bbox[2]:.0f},{bbox[3]:.0f})")
        marks.append(img)
        base = os.path.join(OUT, f"{num}-{slug}")
        img.resize((BASE, BASE), Image.LANCZOS).save(base + ".png")
        img.resize((256, 256), Image.LANCZOS).save(base + "-256.png")
        img.resize((128, 128), Image.LANCZOS).save(base + "-128.png")
    for mode in SHEET_MODES:
        build_sheet(marks, mode).save(os.path.join(OUT, SHEET_MODES[mode]["path"]))
    build_icon(marks[ICON_SRC]).save(ICON_PATH)
    print(f"done -> {OUT}  ({len(CONCEPTS) * 3 + len(SHEET_MODES)} files) + {ICON_PATH}")


if __name__ == "__main__":
    main()
