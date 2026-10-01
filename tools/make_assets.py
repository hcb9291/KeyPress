# -*- coding: utf-8 -*-
#
# 生成项目自带的美术资源。全部由本脚本用代码绘制/合成，
# 不包含任何第三方素材，可自由商用（本项目 MIT，素材视作 CC0）。
#
#   assets/icon.ico        程序图标（多尺寸）
#   assets/icon.png        256x256
#   assets/icon_512.png    512x512
#   assets/mascot.png      吉祥物单独一张（256）
#   assets/header.png      界面顶部横幅（1200x150，含吉祥物）
#   sounds/*.wav           三套提示音（开始音上行 / 停止音下行）
#
# 用法:  python tools/make_assets.py

import math
import os
import struct
import wave
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
SOUNDS = os.path.join(ROOT, "sounds")


# --------------------------------------------------------------------------
# 基础：颜色、图形判断
# --------------------------------------------------------------------------

def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def inside_rounded(u, v, x0, y0, x1, y1, r):
    if u < x0 or u > x1 or v < y0 or v > y1:
        return False
    cx = None
    if u < x0 + r:
        cx = x0 + r
    elif u > x1 - r:
        cx = x1 - r
    cy = None
    if v < y0 + r:
        cy = y0 + r
    elif v > y1 - r:
        cy = y1 - r
    if cx is None or cy is None:
        return True
    return (u - cx) ** 2 + (v - cy) ** 2 <= r * r


def inside_polygon(u, v, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > v) != (yj > v)) and (u < (xj - xi) * (v - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def inside_ellipse(u, v, cx, cy, rx, ry):
    if rx <= 0 or ry <= 0:
        return False
    return ((u - cx) / rx) ** 2 + ((v - cy) / ry) ** 2 <= 1.0


def inside_ring_arc(u, v, cx, cy, r_in, r_out, a0, a1):
    dx, dy = u - cx, v - cy
    d = math.hypot(dx, dy)
    if d < r_in or d > r_out:
        return False
    ang = math.degrees(math.atan2(dy, dx)) % 360.0
    return a0 <= ang <= a1


def star_shape(u, v, cx, cy, r, thin=0.16):
    """四角星光：两个细长的菱形叠在一起。"""
    dx, dy = abs(u - cx), abs(v - cy)
    if dx > r or dy > r:
        return False
    arm = r * thin
    if dx / r + dy / arm <= 1.0:
        return True
    return dy / r + dx / arm <= 1.0


def over(base, color, alpha):
    """把 color(带 alpha) 叠加到 base 上。"""
    if alpha <= 0:
        return base
    br, bg, bb, ba255 = base
    ba = ba255 / 255.0
    r, g, b = color
    na = alpha + ba * (1 - alpha)
    if na <= 0:
        return (0, 0, 0, 0)
    return (int(round((r * alpha + br * ba * (1 - alpha)) / na)),
            int(round((g * alpha + bg * ba * (1 - alpha)) / na)),
            int(round((b * alpha + bb * ba * (1 - alpha)) / na)),
            int(round(na * 255)))


# --------------------------------------------------------------------------
# 吉祥物：猫耳键帽（原创设计）
# --------------------------------------------------------------------------

EAR_OUT = (0xFF, 0x8F, 0xBC)
EAR_IN = (0xFF, 0xC9, 0xDE)
OUTLINE = (0xE0, 0x5C, 0x93)
CAP_TOP = (0xFF, 0xFF, 0xFF)
CAP_BOTTOM = (0xE6, 0xEC, 0xFA)
CAP_SIDE = (0xD5, 0xDD, 0xF2)
EYE = (0x41, 0x42, 0x60)
BLUSH = (0xFF, 0xA6, 0xC6)
MOUTH = (0x8A, 0x6E, 0x8E)

BG_TOP = (0xFF, 0xE2, 0xF1)
BG_BOTTOM = (0xDB, 0xE9, 0xFF)


def mascot_pixel(u, v, simple=False):
    """返回吉祥物在该点的 RGBA（含透明背景）。"""
    # 小尺寸图标：把图形放大、去掉细碎装饰，保证 16/32 像素下也认得出
    if simple:
        zoom = 1.2
        u = (u - 0.5) / zoom + 0.5
        v = (v - 0.5) / zoom + 0.48

    px = (0, 0, 0, 0)

    # 背景：圆角方块 + 上下渐变（超出圆角的部分最后统一裁掉）
    px = over(px, mix(BG_TOP, BG_BOTTOM, v), 1.0)
    if not simple:
        # 梦幻光斑
        if inside_ellipse(u, v, 0.16, 0.10, 0.30, 0.24):
            px = over(px, (0xFF, 0xFF, 0xFF), 0.28)
        if inside_ellipse(u, v, 0.90, 0.94, 0.28, 0.22):
            px = over(px, (0xFF, 0xFF, 0xFF), 0.24)
        # 星光
        for (sx, sy, sr) in ((0.155, 0.245, 0.055), (0.855, 0.215, 0.042),
                             (0.795, 0.735, 0.036), (0.185, 0.795, 0.030)):
            if star_shape(u, v, sx, sy, sr):
                px = over(px, (0xFF, 0xFF, 0xFF), 0.95)
        # 影子
        if inside_ellipse(u, v, 0.50, 0.855, 0.335, 0.030):
            px = over(px, (0xB0, 0x94, 0xBC), 0.13)

    # 猫耳（先画一圈深色描边，小尺寸下轮廓更清楚）
    ears_out = [[(0.200, 0.400), (0.330, 0.115), (0.460, 0.400)],
                [(0.540, 0.400), (0.670, 0.115), (0.800, 0.400)]]
    ears_in = [[(0.277, 0.360), (0.330, 0.200), (0.383, 0.360)],
               [(0.617, 0.360), (0.670, 0.200), (0.723, 0.360)]]
    for ear in ears_out:
        if inside_polygon(u, v, ear):
            px = over(px, OUTLINE, 1.0)
    ears_mid = [[(0.218, 0.385), (0.330, 0.140), (0.442, 0.385)],
                [(0.558, 0.385), (0.670, 0.140), (0.782, 0.385)]]
    for ear in ears_mid:
        if inside_polygon(u, v, ear):
            px = over(px, EAR_OUT, 1.0)
    for ear in ears_in:
        if inside_polygon(u, v, ear):
            px = over(px, EAR_IN, 1.0)

    # 键帽：先画侧面 -> 描边 -> 顶面（有立体感，描边让轮廓更醒目）
    if inside_rounded(u, v, 0.170, 0.585, 0.830, 0.830, 0.150):
        px = over(px, OUTLINE, 1.0)
    if inside_rounded(u, v, 0.185, 0.600, 0.815, 0.815, 0.135):
        px = over(px, CAP_SIDE, 1.0)
    if inside_rounded(u, v, 0.170, 0.315, 0.830, 0.730, 0.150):
        px = over(px, OUTLINE, 1.0)
    if inside_rounded(u, v, 0.185, 0.330, 0.815, 0.720, 0.135):
        px = over(px, mix(CAP_TOP, CAP_BOTTOM, (v - 0.33) / 0.39), 1.0)

    # 腮红
    for bx in (0.303, 0.697):
        if inside_ellipse(u, v, bx, 0.632, 0.062, 0.030):
            px = over(px, BLUSH, 0.85)

    # 眼睛
    for ex in (0.398, 0.602):
        if inside_ellipse(u, v, ex, 0.542, 0.060, 0.082):
            px = over(px, EYE, 1.0)
        if inside_ellipse(u, v, ex - 0.020, 0.508, 0.024, 0.030):
            px = over(px, (0xFF, 0xFF, 0xFF), 1.0)
        if inside_ellipse(u, v, ex + 0.017, 0.578, 0.013, 0.015):
            px = over(px, (0x9F, 0xDB, 0xFF), 1.0)

    # 嘴巴：一小段下弧，看起来在笑
    if inside_ring_arc(u, v, 0.500, 0.574, 0.028, 0.045, 25.0, 155.0):
        px = over(px, MOUTH, 0.95)

    # 裁掉圆角方块之外的部分
    if not inside_rounded(u, v, 0.015, 0.015, 0.985, 0.985, 0.205):
        return (0, 0, 0, 0)
    return px


def render_mascot(size, ss=4, simple=None):
    """渲染吉祥物为 size x size 的 RGBA 像素表。"""
    if simple is None:
        simple = size <= 40          # 小尺寸用简化版，保证看得清
    big = size * ss
    rows = []
    acc = [[None] * size for _ in range(size)]
    for py in range(size):
        row = []
        for px_ in range(size):
            r = g = b = a = 0
            for sy in range(ss):
                for sx in range(ss):
                    u = (px_ * ss + sx + 0.5) / big
                    v = (py * ss + sy + 0.5) / big
                    pr, pg, pb, pa = mascot_pixel(u, v, simple)
                    r += pr * pa
                    g += pg * pa
                    b += pb * pa
                    a += pa
            n = ss * ss
            if a == 0:
                row.append((0, 0, 0, 0))
            else:
                row.append((int(r / a), int(g / a), int(b / a), int(a / n)))
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
# 顶部横幅
# --------------------------------------------------------------------------

BANNER_W, BANNER_H = 1200, 150


def render_banner():
    """界面顶部横幅：柔和渐变 + 星光 + 吉祥物。"""
    ss = 2
    big_w, big_h = BANNER_W * ss, BANNER_H * ss
    mascot_size = 122
    mascot = render_mascot(mascot_size)
    mx0, my0 = 14, (BANNER_H - mascot_size) // 2

    rows = []
    for y in range(BANNER_H):
        row = []
        for x in range(BANNER_W):
            r = g = b = 0
            a = 0
            for sy in range(ss):
                for sx in range(ss):
                    u = (x * ss + sx + 0.5) / big_w
                    v = (y * ss + sy + 0.5) / big_h
                    px = (0, 0, 0, 0)
                    if inside_rounded(u, v, 0.004, 0.02, 0.996, 0.98, 0.16):
                        px = over(px, mix((0xFF, 0xF1, 0xF8), (0xE7, 0xF1, 0xFF), v), 1.0)
                        if inside_ellipse(u, v, 0.10, 0.05, 0.22, 0.22):
                            px = over(px, (0xFF, 0xFF, 0xFF), 0.40)
                        if inside_ellipse(u, v, 0.92, 1.02, 0.26, 0.28):
                            px = over(px, (0xFF, 0xFF, 0xFF), 0.45)
                        for (sxr, syr, sr) in ((0.225, 0.30, 0.020), (0.905, 0.68, 0.017),
                                               (0.80, 0.22, 0.013)):
                            if star_shape(u, v, sxr, syr, sr):
                                px = over(px, (0xFF, 0xFF, 0xFF), 0.85)
                    r += px[0] * px[3]
                    g += px[1] * px[3]
                    b += px[2] * px[3]
                    a += px[3]
            n = ss * ss
            row.append((0, 0, 0, 0) if a == 0 else (int(r / a), int(g / a), int(b / a), int(a / n)))
        rows.append(row)

    # 把吉祥物贴进去
    for y in range(mascot_size):
        for x in range(mascot_size):
            mr, mg, mb, ma = mascot[y][x]
            if ma == 0:
                continue
            ty, tx = y + my0, x + mx0
            if 0 <= ty < BANNER_H and 0 <= tx < BANNER_W:
                base = rows[ty][tx]
                rows[ty][tx] = over(base, (mr, mg, mb), ma / 255.0)
    return rows, BANNER_W, BANNER_H


# --------------------------------------------------------------------------
# 输出 PNG / ICO
# --------------------------------------------------------------------------

def png_bytes(pix, w, h):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            r, g, b, a = pix[y][x]
            raw += bytes((r, g, b, a))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def dib_bytes(pix, size):
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         size * size * 4, 0, 0, 0, 0)
    body = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            r, g, b, a = pix[y][x]
            body += bytes((b, g, r, a))
    mask_row = ((size + 31) // 32) * 4
    body += b"\x00" * (mask_row * size)
    return header + bytes(body)


def write_ico(path, images):
    count = len(images)
    out = bytearray(struct.pack("<HHH", 0, 1, count))
    offset = 6 + 16 * count
    payload = bytearray()
    for size, data in images:
        w = h = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        payload += data
    with open(path, "wb") as fh:
        fh.write(bytes(out) + bytes(payload))


def build_icons():
    os.makedirs(ASSETS, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    rendered = {}
    for s in sizes:
        rendered[s] = render_mascot(s)
        print("  图标 %dx%d" % (s, s))
    write_ico(os.path.join(ASSETS, "icon.ico"),
              [(s, dib_bytes(rendered[s], s)) for s in sizes])
    with open(os.path.join(ASSETS, "icon.png"), "wb") as fh:
        fh.write(png_bytes(rendered[256], 256, 256))
    with open(os.path.join(ASSETS, "mascot.png"), "wb") as fh:
        fh.write(png_bytes(rendered[256], 256, 256))

    big = render_mascot(512, ss=2)
    with open(os.path.join(ASSETS, "icon_512.png"), "wb") as fh:
        fh.write(png_bytes(big, 512, 512))

    banner, bw, bh = render_banner()
    with open(os.path.join(ASSETS, "header.png"), "wb") as fh:
        fh.write(png_bytes(banner, bw, bh))
    print("  横幅 %dx%d" % (bw, bh))


# --------------------------------------------------------------------------
# 提示音
#
# 开始音 = 三个音往上走（明亮、干脆）→ 听起来像"开启"
# 停止音 = 三个音往下走（更低、更长、带低频尾巴）→ 听起来像"停止"
# --------------------------------------------------------------------------

RATE = 22050

TIMBRES = {
    "crisp": ((1.0, 0.22, 0.08), 0.008, 0.07, 0.42),
    "soft": ((1.0, 0.06, 0.00), 0.030, 0.13, 0.34),
    "deep": ((1.0, 0.35, 0.16), 0.012, 0.11, 0.46),
}


def tone(freq, dur, timbre):
    parts, attack, release, amp = TIMBRES[timbre]
    n = int(RATE * dur)
    out = []
    for i in range(n):
        t = i / RATE
        left = t / attack if attack > 0 else 1.0
        right = (dur - t) / release if release > 0 else 1.0
        env = max(0.0, min(1.0, left, right))
        env = env * env * (3 - 2 * env)
        s = 0.0
        for idx, weight in enumerate(parts, start=1):
            if weight:
                s += weight * math.sin(2 * math.pi * freq * idx * t)
        out.append(amp * env * s)
    return out


def silence(dur):
    return [0.0] * int(RATE * dur)


def write_wav(path, samples):
    peak = max(1e-9, max(abs(s) for s in samples))
    scale = min(1.0, 0.92 / peak)
    data = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s * scale)) * 32767))
                    for s in samples)
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RATE)
        fh.writeframes(data)


SOUND_SETS = {
    "chime": {
        "style": "crisp",
        "start": ([659.3, 880.0, 1174.7], [0.07, 0.07, 0.18]),
        "stop": ([1046.5, 784.0, 523.3], [0.07, 0.09, 0.26]),
        "stop_tail": None,
    },
    "soft": {
        "style": "soft",
        "start": ([523.3, 659.3, 784.0], [0.10, 0.10, 0.22]),
        "stop": ([659.3, 523.3, 392.0], [0.10, 0.13, 0.30]),
        "stop_tail": None,
    },
    "deep": {
        "style": "deep",
        "start": ([196.0, 261.6, 329.6], [0.10, 0.10, 0.24]),
        "stop": ([261.6, 196.0, 146.8], [0.10, 0.13, 0.34]),
        "stop_tail": (98.0, 0.34),
    },
}


def build_line(notes, durations, timbre, tail=None):
    out = []
    for i, (freq, dur) in enumerate(zip(notes, durations)):
        if i:
            out += silence(0.012)
        out += tone(freq, dur, timbre)
    if tail:
        out += tone(tail[0], tail[1], timbre)
    return out


def build_sounds():
    os.makedirs(SOUNDS, exist_ok=True)
    for name, spec in SOUND_SETS.items():
        timbre = spec["style"]
        start = build_line(spec["start"][0], spec["start"][1], timbre)
        stop = build_line(spec["stop"][0], spec["stop"][1], timbre, spec.get("stop_tail"))
        write_wav(os.path.join(SOUNDS, name + "_start.wav"), start)
        write_wav(os.path.join(SOUNDS, name + "_stop.wav"), stop)


if __name__ == "__main__":
    print("生成图标 / 横幅 ...")
    build_icons()
    print("生成提示音 ...")
    build_sounds()
    print("完成：", ASSETS)
