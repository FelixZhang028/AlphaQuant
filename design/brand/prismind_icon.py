"""Prismind 镜思 app icon: writes prismind-icon.svg next to this file (run: python prismind_icon.py).

A 60° glass prism with smooth (Apple-style) rounded corners stands in the middle of the picture on a
glossy floor. A soft light source on the left sends a white beam; the light is traced with Snell's
law for 40 wavelengths: violet bends most, red least. The colours are added with screen blending, so
the light is white where they still overlap (inside the glass and just after it) and separates into
a continuous spectrum further away. About 4% is reflected at the first face. The floor reflects the
prism, the beam and the spectrum; caustic light lies beside the base.

Background: aurora glow, a wall that reads as a chart (axes, ticks, a few heat-map cells) and a
faint price-like line behind the beam that goes up and down but is flat overall (no "rising" hint).

The screen with bars on the right (SHOW_SCREEN) and the floating variant were tried and left out.
The small version for 48 px and below is drawn by hand: prismind-icon-small.svg.
"""
import math
import pathlib
import random

here = pathlib.Path(__file__).parent

APEX, LEFT, RIGHT = (256.0, 146.0), (120.0, 382.0), (392.0, 382.0)
BASE_Y, HORIZON = 382, 330
BEAM_Y = 280.0
BEAM_W = 12.0
SCREEN = dict(x=420.0, y=228.0, w=74.0, h=150.0, r=12.0)      # 接光谱的屏幕（站在地面上，靠后一点）
# 棱镜稍微悬空：整体往上抬，光也跟着抬；地面（BASE_Y）不动，阴影和倒影按地面算
# 棱镜（连同地面）往上移 8：棱镜从 138 到 374，正好在画面正中（256）；仍然站在地面上
SHIFT = 22.0
APEX, LEFT, RIGHT = [(x, y - SHIFT) for x, y in (APEX, LEFT, RIGHT)]
BASE_Y, HORIZON = int(BASE_Y - SHIFT), int(HORIZON - SHIFT)
BEAM_Y -= SHIFT
SHOW_SCREEN = False          # 不要右边的屏幕、柱子和分布曲线：光谱一直散到画面边上
PALETTE = ["#9b5cff", "#4c6ef5", "#22b8cf", "#40c057", "#fcc419", "#ff922b", "#ff4d6d"]   # 紫 → 红


def sub(a, b): return (a[0] - b[0], a[1] - b[1])
def add(a, b): return (a[0] + b[0], a[1] + b[1])
def mul(a, k): return (a[0] * k, a[1] * k)
def dot(a, b): return a[0] * b[0] + a[1] * b[1]
def norm(a):
    length = math.hypot(*a)
    return (a[0] / length, a[1] / length)


CENTROID = ((APEX[0] + LEFT[0] + RIGHT[0]) / 3, (APEX[1] + LEFT[1] + RIGHT[1]) / 3)


def outward_normal(p, q):
    d = norm(sub(q, p))
    n = (d[1], -d[0])
    return n if dot(n, sub(mul(add(p, q), 0.5), CENTROID)) > 0 else (-n[0], -n[1])


N_LEFT, N_RIGHT = outward_normal(APEX, LEFT), outward_normal(APEX, RIGHT)


def refract(d, n, eta):
    cosi = -dot(n, d)
    k = 1 - eta * eta * (1 - cosi * cosi)
    return norm(add(mul(d, eta), mul(n, eta * cosi - math.sqrt(k))))


def hit(origin, direction, p, q):
    e = sub(q, p)
    denom = direction[0] * e[1] - direction[1] * e[0]
    t = ((p[0] - origin[0]) * e[1] - (p[1] - origin[1]) * e[0]) / denom
    return add(origin, mul(direction, t))


def to_x(origin, direction, x):
    return add(origin, mul(direction, (x - origin[0]) / direction[0]))


def index(w):
    """Refractive index (higher for violet, spreading more towards blue/violet), exaggerated to be visible."""
    return 1.42 + 0.31 * ((680 - w) / 270) ** 0.9


def palette(t):
    x = max(0.0, min(1.0, t)) * (len(PALETTE) - 1)
    i = min(int(x), len(PALETTE) - 2)
    f = x - i
    f = f * f * (3 - 2 * f)
    a = [int(PALETTE[i][k:k + 2], 16) for k in (1, 3, 5)]
    b = [int(PALETTE[i + 1][k:k + 2], 16) for k in (1, 3, 5)]
    return "#" + "".join(f"{round(a[k] + (b[k] - a[k]) * f):02x}" for k in range(3))


N_MID = index(545)
INCOMING = mul(refract((-1.0, 0.0), (-N_LEFT[0], -N_LEFT[1]), N_MID), -1)
ENTRY = hit((0.0, BEAM_Y), (1.0, 0.0), APEX, LEFT)
perp = (-INCOMING[1], INCOMING[0])
entries = [hit(add(add(ENTRY, mul(perp, s * BEAM_W / 2)), mul(INCOMING, -50)), INCOMING, APEX, LEFT) for s in (-1, 1)]

WAVES = [410 + i * (680 - 410) / 39 for i in range(40)]
SX = SCREEN["x"] if SHOW_SCREEN else 600.0
bands_in, bands_out, landing = [], [], {}
for w in WAVES:
    n = index(w)
    exits, lands = [], []
    for e in entries:
        inside = refract(INCOMING, N_LEFT, 1 / n)
        x = hit(e, inside, APEX, RIGHT)
        out = refract(inside, (-N_RIGHT[0], -N_RIGHT[1]), n)
        exits.append(x)
        lands.append(to_x(x, out, SX))
    colour = palette((w - 410) / 270)
    bands_in.append((colour, [entries[0], exits[0], exits[1], entries[1]]))
    bands_out.append((colour, [exits[0], lands[0], lands[1], exits[1]]))
    landing[w] = (lands[0][1] + lands[1][1]) / 2

beam_start = [to_x(e, INCOMING, -40) for e in entries]
reflected = norm(sub(INCOMING, mul(N_LEFT, 2 * dot(INCOMING, N_LEFT))))
refl_far = [add(e, mul(reflected, 100)) for e in entries]
source = to_x(ENTRY, INCOMING, 6)


def pts(points):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def rounded(points, radii, smooth=0.62):
    out = []
    count = len(points)
    for i, v in enumerate(points):
        prev, nxt = points[i - 1], points[(i + 1) % count]
        a, b = norm(sub(prev, v)), norm(sub(nxt, v))
        angle = math.acos(max(-1.0, min(1.0, dot(a, b))))
        cut = min(radii[i] / math.tan(angle / 2) * 1.25, math.dist(v, prev) * 0.45, math.dist(v, nxt) * 0.45)
        t1, t2 = add(v, mul(a, cut)), add(v, mul(b, cut))
        out.append((t1, add(t1, mul(sub(v, t1), smooth)), add(t2, mul(sub(v, t2), smooth)), t2))
    d = f"M{out[0][3][0]:.2f} {out[0][3][1]:.2f} "
    for i in range(1, count + 1):
        t1, c1, c2, t2 = out[i % count]
        d += f"L{t1[0]:.2f} {t1[1]:.2f} C{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {t2[0]:.2f} {t2[1]:.2f} "
    return d + "Z"


FRONT = rounded([APEX, LEFT, RIGHT], [32, 20, 20])
DEPTH = (26.0, -14.0)
back_left, back_right = add(LEFT, DEPTH), add(RIGHT, DEPTH)


def band_polys(bands, opacity):
    return "\n".join(f'        <polygon points="{pts(p)}" fill="{c}" fill-opacity="{opacity}" style="mix-blend-mode:screen" />' for c, p in bands)


# 屏幕上的七根柱子：每种颜色落在屏幕上的高度，长度高低错落（不是一根比一根长）
BAR_WAVES = [410 + i * 45 for i in range(7)]                  # 紫 → 红
lengths = [0.62, 0.40, 0.86, 0.55, 0.74, 0.44, 0.68]
ys = [landing[min(landing, key=lambda w: abs(w - target))] for target in BAR_WAVES]
spacing = abs(ys[0] - ys[-1]) / 6
bar_h = max(4.0, min(abs(a - b) for a, b in zip(ys, ys[1:])) * 0.68)
bar_x0, bar_max = SX + 7, SCREEN["w"] - 15
bars = []
for i, (w, y) in enumerate(zip(BAR_WAVES, ys)):
    colour = palette((w - 410) / 270)
    length = bar_max * lengths[i]
    bars.append((colour, y, length))
top_bar = min(ys) - bar_h
curve_base = top_bar - 8
curve = []
for i in range(41):
    u = i / 40
    x = bar_x0 + u * bar_max
    z = (u - 0.5) / 0.17
    curve.append((x, curve_base - 26 * math.exp(-0.5 * z * z)))
curve_d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in curve)


def build(quant_extras: bool) -> str:
    rng = random.Random(11)
    # 背景墙上的“坐标图”：坐标轴、刻度、几格热力图（只在第二张）
    chart = ""
    price = ""
    if quant_extras:
        cells = []
        for gx in range(2, 14):
            for gy in range(2, 9):
                if rng.random() < 0.18:
                    tint = rng.choice(["#6366f1", "#22d3ee", "#a855f7", "#3b82f6"])
                    cells.append(f'      <rect x="{gx * 32 + 1}" y="{gy * 32 + 1}" width="30" height="30" rx="3" fill="{tint}" fill-opacity="{rng.uniform(.05, .14):.2f}" />')
        ticks = "\n".join(f'      <line x1="{44 + i * 32}" y1="{HORIZON - 6}" x2="{44 + i * 32}" y2="{HORIZON}" />' for i in range(1, 13)) + "\n" + \
                "\n".join(f'      <line x1="44" y1="{HORIZON - i * 32}" x2="50" y2="{HORIZON - i * 32}" />' for i in range(1, 9))
        chart = f"""    <!-- 墙上像一张坐标图：几格淡淡的热力图、坐标轴和刻度 -->
    <g clip-path="url(#wall)" mask="url(#grid-mask)">
{chr(10).join(cells)}
    </g>
    <g stroke="#c7d2fe" stroke-opacity=".32" stroke-width="1.6" stroke-linecap="round" mask="url(#grid-mask)">
      <line x1="44" y1="60" x2="44" y2="{HORIZON}" />
      <line x1="44" y1="{HORIZON}" x2="470" y2="{HORIZON}" />
{ticks}
    </g>
"""
        # 白光背后一条起伏的“价格线”：有涨有跌，整体是平的
        walk, y = [], 0.0
        for i in range(48):
            y += rng.gauss(0, 4.2)
            y *= 0.86                                   # 往中间拉回，整体不涨不跌
            walk.append((14 + i * 5.2, 236 + y))
        price = '    <polyline points="' + pts(walk) + '" fill="none" stroke="#e0e7ff" stroke-opacity=".38" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" mask="url(#grid-mask)" />\n'

    spectrum = band_polys(bands_out, ".44")
    spectrum_in = band_polys(bands_in, ".2")
    floor_lines = "\n".join(f'      <line x1="250" y1="{HORIZON}" x2="{250 + i * 56}" y2="600" />' for i in range(-14, 15))
    floor_lines += "\n" + "\n".join(f'      <line x1="0" y1="{y:.1f}" x2="512" y2="{y:.1f}" />'
                                   for y in [HORIZON + 4 + 5 * sum(1.38 ** k for k in range(j)) for j in range(1, 9)] if y < 520)
    bar_svg = "\n".join(
        f'      <rect x="{bar_x0:.1f}" y="{y - bar_h / 2:.1f}" width="{length:.1f}" height="{bar_h:.1f}" rx="{bar_h / 2:.1f}" fill="url(#bar-{i})" />'
        for i, (c, y, length) in enumerate(bars))
    bar_glow = "\n".join(f'      <circle cx="{SX + 1:.1f}" cy="{y:.1f}" r="{bar_h * 0.9:.1f}" fill="{c}" fill-opacity=".9" />' for c, y, _ in bars)
    bar_grads = "\n".join(
        f'    <linearGradient id="bar-{i}" x1="{bar_x0}" y1="0" x2="{bar_x0 + bar_max}" y2="0" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{c}" /><stop offset="1" stop-color="{c}" stop-opacity=".55" /></linearGradient>'
        for i, (c, _, _) in enumerate(bars))
    sx, sy, sw, sh, sr = SCREEN["x"], SCREEN["y"], SCREEN["w"], SCREEN["h"], SCREEN["r"]
    screen_bottom = sy + sh

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <title>Prismind 镜思</title>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0b1236" /><stop offset=".55" stop-color="#151a52" /><stop offset="1" stop-color="#271a5f" />
    </linearGradient>
    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
      <path d="M32 0H0V32" fill="none" stroke="#c7d2fe" stroke-opacity=".08" stroke-width="1" />
    </pattern>
    <radialGradient id="grid-fade" cx="256" cy="220" r="300" gradientUnits="userSpaceOnUse">
      <stop offset=".2" stop-color="#fff" /><stop offset="1" stop-color="#fff" stop-opacity="0" />
    </radialGradient>
    <mask id="grid-mask"><rect width="512" height="512" fill="url(#grid-fade)" /></mask>
    <clipPath id="tile"><rect width="512" height="512" rx="116" /></clipPath>
    <clipPath id="wall"><rect width="512" height="{HORIZON}" /></clipPath>
    <clipPath id="floor"><rect y="{HORIZON}" width="512" height="{512 - HORIZON}" /></clipPath>
    <clipPath id="under"><rect y="{BASE_Y}" width="512" height="{512 - BASE_Y}" /></clipPath>
    <clipPath id="front"><path d="{FRONT}" /></clipPath>
    <clipPath id="screen-clip"><rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="{sr}" /></clipPath>
    <filter id="xl" filterUnits="userSpaceOnUse" x="-64" y="-64" width="640" height="640"><feGaussianBlur stdDeviation="46" /></filter>
    <filter id="l" filterUnits="userSpaceOnUse" x="-64" y="-64" width="640" height="640"><feGaussianBlur stdDeviation="14" /></filter>
    <filter id="m" filterUnits="userSpaceOnUse" x="-64" y="-64" width="640" height="640"><feGaussianBlur stdDeviation="7" /></filter>
    <filter id="s" filterUnits="userSpaceOnUse" x="-64" y="-64" width="640" height="640"><feGaussianBlur stdDeviation="3" /></filter>
    <filter id="xs" filterUnits="userSpaceOnUse" x="-64" y="-64" width="640" height="640"><feGaussianBlur stdDeviation="1.2" /></filter>
    <linearGradient id="floor-bg" x1="0" y1="{HORIZON}" x2="0" y2="512" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#1b1f5e" stop-opacity="0" /><stop offset=".15" stop-color="#1b1f5e" stop-opacity=".55" /><stop offset="1" stop-color="#0c1038" stop-opacity=".85" />
    </linearGradient>
    <linearGradient id="floor-fade" x1="0" y1="{HORIZON}" x2="0" y2="512" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff" stop-opacity="0" /><stop offset=".25" stop-color="#fff" stop-opacity=".45" /><stop offset="1" stop-color="#fff" stop-opacity=".9" />
    </linearGradient>
    <mask id="floor-mask"><rect y="{HORIZON}" width="512" height="{512 - HORIZON}" fill="url(#floor-fade)" /></mask>
    <linearGradient id="reflect-fade" x1="0" y1="{BASE_Y}" x2="0" y2="490" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff" stop-opacity=".5" /><stop offset="1" stop-color="#fff" stop-opacity="0" />
    </linearGradient>
    <mask id="reflect-mask"><rect y="{BASE_Y}" width="512" height="{512 - BASE_Y}" fill="url(#reflect-fade)" /></mask>
    <radialGradient id="horizon-glow" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="#818cf8" stop-opacity=".3" /><stop offset="1" stop-color="#818cf8" stop-opacity="0" />
    </radialGradient>
    <radialGradient id="source-glow" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".95" /><stop offset=".18" stop-color="#e0e7ff" stop-opacity=".55" />
      <stop offset=".5" stop-color="#a5b4fc" stop-opacity=".16" /><stop offset="1" stop-color="#a5b4fc" stop-opacity="0" />
    </radialGradient>
    <linearGradient id="beam-fade" x1="0" y1="0" x2="{ENTRY[0]:.1f}" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff" stop-opacity=".7" /><stop offset=".3" stop-color="#fff" stop-opacity=".9" /><stop offset="1" stop-color="#fff" />
    </linearGradient>
    <mask id="beam-mask"><rect x="-64" y="-64" width="640" height="640" fill="url(#beam-fade)" /></mask>
    <linearGradient id="spec-fade" x1="{RIGHT[0] - 60:.0f}" y1="0" x2="520" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff" /><stop offset=".6" stop-color="#fff" stop-opacity=".95" /><stop offset="1" stop-color="#fff" stop-opacity=".7" />
    </linearGradient>
    <mask id="spec-mask"><rect x="-64" y="-64" width="640" height="640" fill="url(#spec-fade)" /></mask>
    <radialGradient id="refl-fade" cx="{ENTRY[0]:.1f}" cy="{ENTRY[1]:.1f}" r="140" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff" /><stop offset="1" stop-color="#fff" stop-opacity="0" />
    </radialGradient>
    <mask id="refl-mask"><rect x="-64" y="-64" width="640" height="640" fill="url(#refl-fade)" /></mask>
    <linearGradient id="refract-fade" x1="0" y1="292" x2="0" y2="{HORIZON + 8}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff" /><stop offset="1" stop-color="#fff" stop-opacity="0" />
    </linearGradient>
    <mask id="refract-mask"><rect width="512" height="512" fill="url(#refract-fade)" /></mask>
    <linearGradient id="face" x1="150" y1="150" x2="380" y2="390" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".26" /><stop offset=".5" stop-color="#c7d2fe" stop-opacity=".10" /><stop offset="1" stop-color="#a5b4fc" stop-opacity=".14" />
    </linearGradient>
    <linearGradient id="edge" x1="130" y1="150" x2="390" y2="385" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#ffffff" stop-opacity=".95" /><stop offset=".6" stop-color="#dbe4ff" stop-opacity=".75" /><stop offset="1" stop-color="#c5f6fa" stop-opacity=".85" />
    </linearGradient>
    <linearGradient id="bevel" x1="0" y1="150" x2="0" y2="382" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff" stop-opacity=".55" /><stop offset=".55" stop-color="#fff" stop-opacity=".08" /><stop offset="1" stop-color="#fff" stop-opacity=".22" />
    </linearGradient>
    <linearGradient id="screen-fill" x1="0" y1="{sy}" x2="0" y2="{screen_bottom}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#1e2470" stop-opacity=".75" /><stop offset="1" stop-color="#0d1140" stop-opacity=".85" />
    </linearGradient>
    <linearGradient id="screen-edge" x1="{sx}" y1="{sy}" x2="{sx + sw}" y2="{screen_bottom}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#e0e7ff" stop-opacity=".55" /><stop offset="1" stop-color="#a5b4fc" stop-opacity=".18" />
    </linearGradient>
    <linearGradient id="screen-sheen" x1="0" y1="{sy}" x2="0" y2="{sy + sh * 0.55}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff" stop-opacity=".09" /><stop offset="1" stop-color="#fff" stop-opacity="0" />
    </linearGradient>
{bar_grads}
    <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fff" stop-opacity=".09" /><stop offset=".42" stop-color="#fff" stop-opacity="0" />
    </linearGradient>
    <radialGradient id="vignette" cx="256" cy="230" r="360" gradientUnits="userSpaceOnUse">
      <stop offset=".55" stop-color="#000" stop-opacity="0" /><stop offset="1" stop-color="#000" stop-opacity=".36" />
    </radialGradient>
    <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#fff" stop-opacity=".28" /><stop offset=".5" stop-color="#fff" stop-opacity=".07" /><stop offset="1" stop-color="#fff" stop-opacity=".03" />
    </linearGradient>

    <g id="light">
      <g mask="url(#beam-mask)">
        <polygon points="{pts([beam_start[0], entries[0], entries[1], beam_start[1]])}" fill="#dfe6ff" opacity=".35" filter="url(#m)" />
        <polygon points="{pts([beam_start[0], entries[0], entries[1], beam_start[1]])}" fill="#ffffff" opacity=".92" filter="url(#xs)" />
      </g>
      <g mask="url(#refl-mask)">
        <polygon points="{pts([entries[0], refl_far[0], refl_far[1], entries[1]])}" fill="#ffffff" opacity=".07" filter="url(#m)" />
      </g>
      <g style="isolation:isolate" mask="url(#spec-mask)">
        <g filter="url(#l)" opacity=".5">
{spectrum}
        </g>
        <g filter="url(#xs)">
{spectrum}
        </g>
      </g>
    </g>
    <g id="screen">
      <rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="{sr}" fill="url(#screen-fill)" />
      <g clip-path="url(#screen-clip)">
        <rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" fill="url(#screen-sheen)" />
        <!-- 光落在屏幕上：七种颜色各变成一根柱子 -->
        <g filter="url(#m)" opacity=".55">
{bar_svg}
        </g>
{bar_svg}
        <g filter="url(#s)">
{bar_glow}
        </g>
      </g>
      <rect x="{sx + .75}" y="{sy + .75}" width="{sw - 1.5}" height="{sh - 1.5}" rx="{sr - .75}" fill="none" stroke="url(#screen-edge)" stroke-width="1.5" />
    </g>
  </defs>

  <!-- 底板 -->
  <rect width="512" height="512" rx="116" fill="url(#bg)" />
  <g clip-path="url(#tile)">
    <g filter="url(#xl)">
      <ellipse cx="70" cy="90" rx="190" ry="140" fill="#22d3ee" fill-opacity=".14" />
      <ellipse cx="400" cy="70" rx="170" ry="120" fill="#6366f1" fill-opacity=".2" />
      <ellipse cx="470" cy="470" rx="220" ry="160" fill="#d946ef" fill-opacity=".14" />
      <ellipse cx="120" cy="470" rx="170" ry="120" fill="#3b82f6" fill-opacity=".12" />
    </g>
    <g clip-path="url(#wall)"><rect width="512" height="512" fill="url(#grid)" mask="url(#grid-mask)" /></g>
{chart}{price}    <rect y="{HORIZON}" width="512" height="{512 - HORIZON}" fill="url(#floor-bg)" />
    <g clip-path="url(#floor)" mask="url(#floor-mask)" stroke="#a5b4fc" stroke-opacity=".2" stroke-width="1.2">
{floor_lines}
    </g>
    <ellipse cx="250" cy="{HORIZON}" rx="270" ry="14" fill="url(#horizon-glow)" />

    <!-- 光源：左边一团柔和的光 -->
    <circle cx="{source[0] - 16:.1f}" cy="{source[1] + 6:.1f}" r="110" fill="url(#source-glow)" opacity=".75" />
    <circle cx="{source[0] - 10:.1f}" cy="{source[1] + 4:.1f}" r="34" fill="url(#source-glow)" />

    <!-- 光滑地面上的倒影：光、光谱和屏幕 -->
    <g clip-path="url(#under)" mask="url(#reflect-mask)" opacity=".45">
      <g transform="translate(0 {2 * BASE_Y}) scale(1 -1)"><use href="#light" />{'<use href="#screen" />' if SHOW_SCREEN else ''}</g>
    </g>
    <!-- 焦散：光穿过玻璃，在地面上聚成几道明亮的光纹 -->
    <g filter="url(#s)" fill="none" stroke-linecap="round">
      <path d="M {RIGHT[0] - 6:.0f} {BASE_Y + 8} Q {RIGHT[0] + 22:.0f} {BASE_Y + 2} {RIGHT[0] + 40:.0f} {BASE_Y + 12}" stroke="#ffffff" stroke-opacity=".55" stroke-width="2.4" />
      <path d="M {RIGHT[0] + 2:.0f} {BASE_Y + 16} Q {RIGHT[0] + 30:.0f} {BASE_Y + 10} {RIGHT[0] + 52:.0f} {BASE_Y + 22}" stroke="#f0abfc" stroke-opacity=".45" stroke-width="2" />
      <path d="M {RIGHT[0] - 14:.0f} {BASE_Y + 24} Q {RIGHT[0] + 18:.0f} {BASE_Y + 18} {RIGHT[0] + 44:.0f} {BASE_Y + 30}" stroke="#67e8f9" stroke-opacity=".4" stroke-width="2" />
    </g>
    <ellipse cx="{RIGHT[0] + 22:.0f}" cy="{BASE_Y + 16}" rx="44" ry="10" fill="#c7d2fe" fill-opacity=".12" filter="url(#m)" />
  </g>

  <!-- 接触阴影：紧贴底面的深色阴影 + 一圈更大更淡的阴影 + 前沿一条细细的接触线 -->
  <g clip-path="url(#tile)">
    <ellipse cx="{(LEFT[0] + back_right[0]) / 2:.0f}" cy="{BASE_Y - 2}" rx="168" ry="22" fill="#02030f" fill-opacity=".7" filter="url(#m)" />
    <polygon points="{pts([add(LEFT, (-4, 2)), add(back_left, (0, -2)), add(back_right, (4, -2)), add(RIGHT, (4, 2))])}" fill="#02030f" fill-opacity=".85" filter="url(#s)" />
    <line x1="{LEFT[0] + 14}" y1="{BASE_Y + 3}" x2="{RIGHT[0] - 14}" y2="{BASE_Y + 3}" stroke="#000" stroke-opacity=".55" stroke-width="5" stroke-linecap="round" filter="url(#xs)" />
{f'    <ellipse cx="{sx + sw / 2:.0f}" cy="{screen_bottom + 1:.0f}" rx="{sw * 0.62:.0f}" ry="7" fill="#02030f" fill-opacity=".75" filter="url(#s)" />' if SHOW_SCREEN else ''}
    <g clip-path="url(#under)" mask="url(#reflect-mask)">
      <g transform="translate(0 {2 * BASE_Y}) scale(1 -1)">
        <path d="{FRONT}" fill="url(#face)" />
        <path d="{FRONT}" fill="none" stroke="url(#edge)" stroke-width="3" opacity=".5" />
      </g>
    </g>
  </g>

{'  <use href="#screen" />' if SHOW_SCREEN else ''}

  <!-- 光 -->
  <g clip-path="url(#tile)"><use href="#light" /></g>

  <!-- 三棱镜：正面玻璃 -->
  <path d="{FRONT}" fill="url(#face)" />
  <g clip-path="url(#front)">
    <g mask="url(#refract-mask)" opacity=".9">
      <rect width="512" height="512" fill="#141a52" fill-opacity=".45" />
      <g transform="translate(8 -5) rotate(-2 256 280)"><rect x="-40" y="-40" width="600" height="600" fill="url(#grid)" opacity="1.5" /></g>
    </g>
    <g style="isolation:isolate">
      <g filter="url(#m)" opacity=".35">
{spectrum_in}
      </g>
      <g filter="url(#xs)" opacity=".75">
{spectrum_in}
      </g>
    </g>
    <path d="{FRONT}" fill="none" stroke="url(#bevel)" stroke-width="14" opacity=".35" filter="url(#s)" />
  </g>
  <path d="{FRONT}" fill="none" stroke="url(#edge)" stroke-width="3.5" />

  <g clip-path="url(#tile)">
    <rect width="512" height="512" fill="url(#vignette)" />
    <rect width="512" height="512" fill="url(#sheen)" />
  </g>
  <rect x="1.5" y="1.5" width="509" height="509" rx="114.5" fill="none" stroke="url(#rim)" stroke-width="3" />
</svg>
"""


(here / "prismind-icon.svg").write_text(build(True), encoding="utf-8")
print("written:", here / "prismind-icon.svg")
