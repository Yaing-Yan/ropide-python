# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
"""把 1bpp 位图渲染成终端字符。
   braille : 1 字符 = 2×4 点。配合 --vscale 2 → 1 字符承载 2×8 源像素。
   sextant/half/ascii 作为兼容后备。
"""

# 盲文点位：BITS[dy][dx]
BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))
HALF = {0: " ", 1: "▀", 2: "▄", 3: "█"}


def _sample(rows, w, h, x, y, hs, vs):
    """把 hs×vs 个源像素 OR 成一个点"""
    for sy in range(vs):
        yy = y + sy
        if yy >= h:
            break
        row = rows[yy]
        for sx in range(hs):
            xx = x + sx
            if xx < w and row[xx]:
                return 1
    return 0


def render_braille(rows, w, h, hscale=1, vscale=1, invert=False):
    out = []
    cw, ch = 2 * hscale, 4 * vscale
    for y0 in range(0, h, ch):
        line = []
        for x0 in range(0, w, cw):
            bits = 0
            for dy in range(4):
                for dx in range(2):
                    if _sample(rows, w, h,
                               x0 + dx * hscale, y0 + dy * vscale, hscale, vscale):
                        bits |= BITS[dy][dx]
            if invert:
                bits ^= 0xFF
            line.append(chr(0x2800 | bits))
        out.append("".join(line))
    return out


def render_half(rows, w, h, hscale=1, vscale=1, invert=False):
    out = []
    for y0 in range(0, h, 2 * vscale):
        line = []
        for x0 in range(0, w, hscale):
            t = _sample(rows, w, h, x0, y0, hscale, vscale)
            b = _sample(rows, w, h, x0, y0 + vscale, hscale, vscale)
            v = t | (b << 1)
            if invert:
                v ^= 3
            line.append(HALF[v])
        out.append("".join(line))
    return out


def render_ascii(rows, w, h, hscale=1, vscale=1, invert=False):
    out = []
    for y0 in range(0, h, vscale):
        line = []
        for x0 in range(0, w, hscale):
            on = _sample(rows, w, h, x0, y0, hscale, vscale)
            if invert:
                on ^= 1
            line.append("#" if on else " ")
        out.append("".join(line))
    return out


RENDERERS = {"braille": render_braille, "half": render_half, "ascii": render_ascii}
