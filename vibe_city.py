#!/usr/bin/env python3
"""
VIBE CITY - a neon coastal city that lives in your terminal.

A fan-made tribute for the GTA VI launch. The map, district names, signs and
radio stations are all original; not affiliated with or endorsed by
Rockstar Games or Take-Two.

Run:   python3 vibe_city.py            (256-colour terminal, ~120x40 or bigger is best)
       python3 vibe_city.py --ascii    (if your terminal mangles the Unicode glyphs)

Keys:  arrows / WASD move   TAB sprint   G ghost   M city map   ? help   Q quit
"""
import base64
import curses
import locale
import math
import os
import random
import sys
import time
import zlib

W, H = 180, 60
SEED = 1986

(OCEAN, BAY, CANAL, SAND, SANDPALM, GRASS, PALM, ROAD, HWY, BRIDGE,
 TOWER, HOTEL, HOUSE, RUNWAY, TARMAC, DOCK, CONTAINER) = range(17)
WATER = {OCEAN, BAY, CANAL}
SOLID = WATER | {TOWER, HOTEL, CONTAINER}
ROADISH = {ROAD, HWY, BRIDGE}
BRIDGE_ROWS = (10, 23, 37, 50)

TOWER_BG = [53, 54, 55, 17, 89, 23]
WINDOW_FG = [229, 51, 213]
HOTEL_BG = [218, 159, 229, 183, 152, 224]
HOUSE_FG = [216, 210, 223, 181]
CONTAINER_FG = [196, 208, 27, 34, 124]
CAR_FG = [196, 226, 201, 51, 46, 231, 208]

ASCII_MAP = str.maketrans({
    "♣": "T", "⌂": "^", "▪": "#", "═": "=", "║": "|", "│": "|", "─": "-",
    "▆": "#", "◆": "@", "▶": ">", "▼": "v", "◀": "<", "▲": "^", "♪": "~",
    "▮": "#", "▯": "-", "█": "#", "·": ".", "—": "-", "★": "*", "╱": "/",
    "╲": "\\", "░": ":", "●": "o", "┼": "+", "┬": "+", "▄": "_", "▀": "-",
    "┃": "|", "▬": "=", "╮": ".", "°": "o", "•": ".", "▮": "#",
})

DISTRICTS = {
    # name: (vibes 1-5, tagline)
    "Neon Shores":        (5, "pastel hotels, all-night surf"),
    "Flamingo Keys":      (5, "tiny islands, big money"),
    "The Big Blue":       (4, "nothing but horizon"),
    "Vibe Bay":           (4, "yachts, jet skis, bad decisions"),
    "Vibe Causeway":      (4, "six lanes of sunset"),
    "Chrome Heights":     (4, "glass towers, neon rooftops"),
    "Palmetto Downs":     (3, "lawns, palms, suspicious BBQs"),
    "Mango Gardens":      (3, "canals, gators, mango trees"),
    "Vibe Int'l Airport": (2, "now boarding: everyone"),
    "Starlight Docks":    (2, "containers full of who-knows"),
    "Starlight Channel":  (3, "cargo ships at dusk"),
    "I-Vibe Expressway":  (3, "never not under construction"),
    "Route 86":           (3, "the long way to the beach"),
}

RADIO = [
    ("NEON WAVE 88.6", "Midnight Palms"),
    ("FLAMINGO FM", "Pastel Suits"),
    ("CHROME RADIO", "Heat Mirage"),
    ("BAYSIDE SOUL", "Low Tide Love"),
    ("STATIC 103", "Six Lanes of Sunset"),
]

SIGNS = [  # (x, y, text) - island signs positioned along Neon Shores & mainland
    (135, 8, "MOTEL"), (135, 18, "NEON"), (135, 27, "DISCO"),
    (135, 36, "SURF"), (135, 45, "HOTEL"),
    (25, 8, "VIBE"), (45, 11, "CLUB86"), (30, 14, "CHROME"), (52, 13, "PALMS"),
    (22, 44, "VIBE INTL"),
    (30, 28, "GAS"),
]

LABELS = [
    ("VIBE INT'L AIRPORT", 15, 40), ("MANGO GARDENS", 17, 31),
    ("CHROME HEIGHTS", 28, 12), ("PALMETTO DOWNS", 28, 20),
    ("STARLIGHT DOCKS", 50, 44), ("VIBE BAY", 93, 4),
    ("FLAMINGO KEYS", 91, 34), ("NEON SHORES", 134, 2),
    ("THE BIG BLUE", 165, 28),
]


# --------------------------------------------------------------------------- colours

BASE16 = [(0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0), (0, 0, 128), (128, 0, 128),
          (0, 128, 128), (192, 192, 192), (128, 128, 128), (255, 0, 0), (0, 255, 0),
          (255, 255, 0), (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255)]


def rgb(c):
    if c < 16:
        return BASE16[c]
    if c < 232:
        c -= 16
        lv = (0, 95, 135, 175, 215, 255)
        return lv[c // 36], lv[(c // 6) % 6], lv[c % 6]
    v = 8 + (c - 232) * 10
    return v, v, v


def nearest(c, n):
    r, g, b = rgb(c)
    return min(range(n), key=lambda i: (BASE16[i][0] - r) ** 2 + (BASE16[i][1] - g) ** 2
               + (BASE16[i][2] - b) ** 2)


class Palette:
    """Hands out curses colour pairs on demand; maps 256 colours down if needed."""

    def __init__(self):
        self.ok = curses.has_colors()
        self.n = curses.COLORS if self.ok else 0
        self.max = min(curses.COLOR_PAIRS - 1, 255) if self.ok else 0
        self.reset()

    def reset(self):
        self.cache, self.next, self.full = {}, 1, False

    def __call__(self, fg, bg):
        if not self.ok:
            return 0
        a = self.cache.get((fg, bg))
        if a is None:
            if self.next > self.max:
                self.full = True  # caller resets and redraws the frame
                return 0
            f, b = fg, bg
            if self.n < 256:
                f, b = nearest(fg, min(self.n, 16)), nearest(bg, min(self.n, 16))
            curses.init_pair(self.next, f, b)
            a = curses.color_pair(self.next)
            self.cache[(fg, bg)] = a
            self.next += 1
        return a


# --------------------------------------------------------------------------- day & night

CLOCK_START = 16 * 60   # the city opens at 16:00, so the first sunset comes after ~40 s
CLOCK_SPEED = 4         # game minutes per real second: a full day takes 6 minutes

# night colour -> its daytime look; anything not listed keeps its colour
DAY_MAP = {
    18: 32, 17: 32, 25: 38, 39: 117, 159: 231,          # ocean: navy -> turquoise
    23: 37, 44: 123, 30: 44, 51: 159,                   # bay & canals
    22: 71, 71: 150, 48: 28, 28: 22,                    # grass, palms
    223: 230, 137: 180,                                  # sand
    237: 245, 236: 244, 238: 247, 240: 250, 220: 226, 250: 255,  # roads, tarmac, docks
    53: 146, 54: 140, 55: 104, 89: 182, 60: 195,         # glass towers, unlit windows
}
_TINT = {}


def _nearest256(r, g, b):
    return min(range(16, 256), key=lambda c: sum((p - q) ** 2 for p, q in zip(rgb(c), (r, g, b))))


def tint(c, day):
    """Blend a night colour toward its day colour; day goes 0 (night) .. 1 (noon)."""
    if day <= 0 or c not in DAY_MAP:
        return c
    q = round(day * 6)  # a few fixed steps keeps the colour-pair count small
    key = (c, q)
    if key not in _TINT:
        a, b, f = rgb(c), rgb(DAY_MAP[c]), q / 6
        _TINT[key] = DAY_MAP[c] if q == 6 else _nearest256(*(int(x + (y - x) * f) for x, y in zip(a, b)))
    return _TINT[key]


def clock_minutes(now, offset=0):
    return int(CLOCK_START + offset + now * CLOCK_SPEED) % (24 * 60)


def daylight(m):
    """0 at night, 1 by day; sunrise 06:00-07:30, sunset 18:30-20:00."""
    if 6 * 60 <= m < 7 * 60 + 30:
        return (m - 6 * 60) / 90
    if 7 * 60 + 30 <= m < 18 * 60 + 30:
        return 1.0
    if 18 * 60 + 30 <= m < 20 * 60:
        return 1 - (m - (18 * 60 + 30)) / 90
    return 0.0


def lit_fraction(m, day):
    """Share of windows lit: few by day, rising through the night, peaking around 02:00."""
    hours_after_dusk = ((m - 20 * 60) % (24 * 60)) / 60  # 0 at 20:00, 6 at 02:00
    if hours_after_dusk <= 6:
        night = 0.5 + 0.35 * hours_after_dusk / 6
    elif hours_after_dusk <= 9:
        night = 0.85 - 0.35 * (hours_after_dusk - 6) / 3   # people go to bed by 05:00
    else:
        night = 0.5
    return 0.08 * day + night * (1 - day)


def phase_name(m):
    if 5 * 60 <= m < 7 * 60 + 30:
        return "DAWN"
    if 7 * 60 + 30 <= m < 18 * 60 + 30:
        return "DAY"
    if 18 * 60 + 30 <= m < 20 * 60 + 30:
        return "DUSK"
    return "NIGHT"


def flush(scr, pal, grid, y0, ascii_mode):
    """Write rows of (ch, fg, bg, bold) cells, batching runs that share a colour."""
    for i, row in enumerate(grid):
        x, runs = 0, []
        for ch, fg, bg, bold in row:
            a = pal(fg, bg) | (curses.A_BOLD if bold else 0)
            if runs and runs[-1][0] == a:
                runs[-1][1].append(ch)
            else:
                runs.append((a, [ch]))
        for a, chs in runs:
            s = "".join(chs)
            if ascii_mode:
                s = s.translate(ASCII_MAP)
            try:
                scr.addstr(y0 + i, x, s, a)
            except curses.error:
                pass  # bottom-right cell; curses complains after writing it
            x += len(s)


# --------------------------------------------------------------------------- the city

class World:
    def __init__(self, seed=SEED):
        rnd = random.Random(seed)
        self.g = g = [[OCEAN] * W for _ in range(H)]
        self.h = [[rnd.randrange(1000) for _ in range(W)] for _ in range(H)]
        land = [[False] * W for _ in range(H)]
        self.vert = set()
        self.hwy_v = set()
        self.hwy_h = set()
        self.runway_dash = set()
        self.runway_edge = set()

        sx, sy = W / 116.0, H / 80.0

        def to_world(pts):
            return [(px * sx, py * sy) for px, py in pts]

        def set_cell(x, y, tile, is_land=True, only_land=False):
            ix, iy = int(round(x)), int(round(y))
            if 0 <= ix < W and 0 <= iy < H:
                if only_land and not land[iy][ix]:
                    return
                g[iy][ix] = tile
                if is_land:
                    land[iy][ix] = True

        def fill_poly(points, tile, is_land=True, only_land=False):
            pts = to_world(points)
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            min_x, max_x = max(0, int(min(xs))), min(W - 1, int(max(xs)))
            min_y, max_y = max(0, int(min(ys))), min(H - 1, int(max(ys)))
            n = len(pts)
            for y in range(min_y, max_y + 1):
                for x in range(min_x, max_x + 1):
                    inside = False
                    p1x, p1y = pts[0]
                    for i in range(1, n + 1):
                        p2x, p2y = pts[i % n]
                        if y > min(p1y, p2y) and y <= max(p1y, p2y) and x <= max(p1x, p2x):
                            if p1y != p2y:
                                xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                            if p1x == p2x or x <= xinters:
                                inside = not inside
                        p1x, p1y = p2x, p2y
                    if inside:
                        set_cell(x, y, tile, is_land, only_land)

        def fill_ellipse(cx, cy, rx, ry, tile, is_land=True, only_land=False):
            wcx, wcy, wrx, wry = cx * sx, cy * sy, rx * sx, ry * sy
            for y in range(max(0, int(wcy - wry - 1)), min(H, int(wcy + wry + 2))):
                for x in range(max(0, int(wcx - wrx - 1)), min(W, int(wcx + wrx + 2))):
                    if ((x - wcx) / wrx) ** 2 + ((y - wcy) / wry) ** 2 <= 1.0:
                        set_cell(x, y, tile, is_land, only_land)

        def draw_line_v(x0, y0, x1, y1, radius, tile, is_land=True, only_land=False):
            wx0, wy0, wx1, wy1 = x0 * sx, y0 * sy, x1 * sx, y1 * sy
            wrx, wry = max(0.5, radius * sx), max(0.5, radius * sy)
            steps = int(max(abs(wx1 - wx0), abs(wy1 - wy0)) * 2) + 1
            for i in range(steps + 1):
                t = i / steps
                cx = wx0 + (wx1 - wx0) * t
                cy = wy0 + (wy1 - wy0) * t
                for y in range(max(0, int(cy - wry - 1)), min(H, int(cy + wry + 2))):
                    for x in range(max(0, int(cx - wrx - 1)), min(W, int(cx + wrx + 2))):
                        if ((x - cx) / wrx) ** 2 + ((y - cy) / wry) ** 2 <= 1.0:
                            set_cell(x, y, tile, is_land, only_land)

        # 1. West Mainland Base & Sandy North Shore (from vice_city_map.py)
        mainland = [
            (8, 7), (38, 7), (43, 12), (41, 22), (44, 32), (43, 45),
            (46, 54), (47, 68), (41, 73), (28, 72), (24, 74), (8, 73),
            (6, 52), (8, 30),
        ]
        fill_poly(mainland, GRASS)
        draw_line_v(10, 7.5, 37, 7.5, 1.3, SAND)  # North Downtown beach

        # Mainland Districts (respecting the organic mainland silhouette)
        parks = {}
        for y in range(H):
            for x in range(W):
                if not land[y][x] or g[y][x] == SAND:
                    continue
                if 7 <= y <= 15:  # Downtown -> Chrome Heights
                    blk = (x // 9, y // 4)
                    if blk not in parks:
                        parks[blk] = rnd.random() < 0.14
                    if parks[blk]:
                        g[y][x] = PALM if rnd.random() < 0.3 else GRASS
                    else:
                        g[y][x] = TOWER
                elif 16 <= y <= 26:  # Little Haiti -> Palmetto Downs
                    r = rnd.random()
                    g[y][x] = HOUSE if r < 0.42 else (PALM if r < 0.58 else GRASS)
                elif 27 <= y <= 37:  # Little Havana -> Mango Gardens
                    r = rnd.random()
                    g[y][x] = HOUSE if r < 0.25 else (PALM if r < 0.40 else GRASS)
                elif y >= 38 and x < 43:
                    if y < 43:  # Fort Baxter green/military belt
                        g[y][x] = TARMAC if x < 34 else GRASS
                    else:  # Escobar Intl -> Vibe Int'l Airport
                        g[y][x] = TARMAC
                elif y >= 38 and x >= 43:  # Sunshine Autos & Viceport -> Starlight Docks
                    g[y][x] = CONTAINER if (y % 2 == 1 and x % 4 and x < 68 and rnd.random() < 0.65) else DOCK

        # Winding canal through Mango Gardens
        for x in range(12, 42):
            cy = 32 + int(2 * math.sin(x * 0.2))
            if 0 <= cy < H and land[cy][x]:
                g[cy][x] = CANAL

        # Airport X-shaped crossed runways & terminal
        for x0, y0, x1, y1 in ((10, 61, 24, 70), (9, 69, 24, 61)):
            wx0, wy0, wx1, wy1 = x0 * sx, y0 * sy, x1 * sx, y1 * sy
            steps = int(max(abs(wx1 - wx0), abs(wy1 - wy0)) * 3) + 1
            for i in range(steps + 1):
                t = i / steps
                cx, cy = wx0 + (wx1 - wx0) * t, wy0 + (wy1 - wy0) * t
                ix, iy = int(round(cx)), int(round(cy))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = ix + dx, iy + dy
                        if 0 <= nx < W and 0 <= ny < H and land[ny][nx] and g[ny][nx] in (TARMAC, RUNWAY):
                            if abs(dx) + abs(dy) <= 1:
                                g[ny][nx] = RUNWAY
                                if dx == 0 and dy == 0 and i % 4 < 2:
                                    self.runway_dash.add((nx, ny))
                                elif i % 6 == 0:
                                    self.runway_edge.add((nx, ny))
        for y in (43, 44):
            for x in range(21, 30):
                if land[y][x]:
                    g[y][x] = HOTEL

        # Viceport 3 protruding harbor piers
        for py in (45, 48, 51):
            for x in range(66, 77):
                set_cell(x, py, DOCK, is_land=True)

        # 2. Central Bay Islands -> Flamingo Keys (from vice_city_map.py)
        # Prawn Island
        fill_ellipse(61, 14, 7.2, 5.2, GRASS)
        fill_ellipse(61, 15, 5.8, 3.5, HOUSE)
        for y in range(7, 15):
            for x in range(84, 106):
                if g[y][x] == HOUSE and rnd.random() < 0.55:
                    g[y][x] = PALM if rnd.random() < 0.35 else GRASS

        # Leaf Links (3 Golf Course Islands + sandy golf cart path)
        fill_ellipse(63, 25, 5.2, 3.0, GRASS)
        fill_ellipse(64, 32, 6.5, 4.0, GRASS)
        fill_ellipse(63, 39, 5.2, 3.0, GRASS)
        for y in range(18, 30):
            if land[y][98]:
                g[y][98] = SAND

        # Starfish Island (sandy beach ring + lush estate interior)
        fill_ellipse(63, 50, 10.2, 5.8, SAND)
        fill_ellipse(63, 50, 9.0, 4.6, GRASS)
        for y in range(34, 42):
            for x in range(85, 112):
                if g[y][x] == GRASS and rnd.random() < 0.25:
                    g[y][x] = HOUSE

        # 3. East Island -> Neon Shores (from vice_city_map.py)
        east_island = [
            (82, 6), (101, 6), (105, 16), (104, 34), (102, 52),
            (99, 69), (93, 75), (86, 72), (82, 62), (80, 46),
            (79, 28), (80, 14),
        ]
        fill_poly(east_island, HOTEL)
        fill_poly([(78, 5), (98, 5), (98, 28), (78, 28)], GRASS, only_land=True)  # Vice Point parks

        # Sprinkle pastel resort hotels in Vice Point & palm fringe along bayshore
        for y in range(6, 21):
            for x in range(124, 150):
                if land[y][x] and g[y][x] == GRASS and x >= 134 and (y % 4 in (1, 2)) and rnd.random() < 0.45:
                    g[y][x] = HOTEL

        # Continuous Golden Eastern Beach
        beach_strip = [
            (96, 6), (101, 6), (105, 16), (104, 34), (102, 52),
            (99, 69), (93, 75), (88, 73), (94, 67), (97, 51),
            (98, 34), (98, 16),
        ]
        fill_poly(beach_strip, SAND)
        for y in range(H):
            for x in range(W):
                if g[y][x] == SAND and rnd.random() < 0.12:
                    g[y][x] = SANDPALM

        # 4. Coastal Bathymetry (shallow turquoise BAY hugging coastlines, deep OCEAN further out)
        for y in range(H):
            for x in range(W):
                if not land[y][x]:
                    min_d = 99.0
                    for dy in range(-4, 5):
                        ny = y + dy
                        if not (0 <= ny < H):
                            continue
                        for dx in range(-7, 8):
                            nx = x + dx
                            if 0 <= nx < W and land[ny][nx]:
                                d = math.hypot(dx * 0.5, dy)
                                if d < min_d:
                                    min_d = d
                    g[y][x] = BAY if min_d <= 3.5 else OCEAN

        # 5. Major Avenues, Expressways & Four East-West Bridges
        def lay_road(x, y, tile=ROAD, vertical=False):
            if not (0 <= x < W and 0 <= y < H):
                return
            if g[y][x] in WATER:
                g[y][x] = BRIDGE
                if vertical:
                    self.vert.add((x, y))
            else:
                g[y][x] = tile

        # Mainland secondary streets inside Downtown & suburbs for crisp navigable blocks
        for x in (15, 31, 50):
            for y in range(7, 27):
                if land[y][x] and g[y][x] not in (SAND, SANDPALM):
                    lay_road(x, y, ROAD, vertical=True)
        for y in (7, 13, 20, 31):
            for x in range(13, 66):
                if land[y][x] and g[y][x] not in (SAND, SANDPALM, CANAL):
                    lay_road(x, y, ROAD)

        # Mainland primary avenues (matching vice_city_map.py)
        for y in range(7, 43):  # West Ave
            if land[y][22]:
                lay_road(22, y, ROAD, vertical=True)
        for y in range(7, 53):  # Central Spine (I-Vibe Expressway)
            for x in (40, 41):
                if land[y][x]:
                    lay_road(x, y, HWY, vertical=True)
                    if x == 40:
                        self.hwy_v.add((x, y))
        for y in range(9, 52):  # East Bayshore Ave
            if land[y][60]:
                lay_road(60, y, ROAD, vertical=True)

        # Mainland east-west boulevards
        for x in range(15, 67):
            if land[10][x]:
                lay_road(x, 10, ROAD)
            if land[16][x]:
                lay_road(x, 16, ROAD)
            if land[23][x]:
                lay_road(x, 23, ROAD)
        for y in (27, 37):  # Route 86 & Starfish approach
            for x in range(12, 68):
                if land[y][x]:
                    lay_road(x, y, HWY)
                    self.hwy_h.add((x, y))
        for x in range(40, 73):  # Viceport South Bridge approach
            if land[50][x]:
                lay_road(x, 50, ROAD)
        # Connect airport apron & terminal to main road network
        for x in range(22, 41):
            if land[42][x]:
                lay_road(x, 42, ROAD)

        # East Island avenues (Bayshore & Ocean Drive) + cross streets
        for y in range(7, 51):
            bx = 129 if y <= 46 else 129 + (y - 46)
            ox = 145 if y <= 47 else 145 - (y - 47)
            if land[y][bx]:
                lay_road(bx, y, ROAD, vertical=True)
            if y > 46 and land[y][bx - 1]:
                lay_road(bx - 1, y, ROAD, vertical=True)
            if land[y][ox]:
                lay_road(ox, y, ROAD, vertical=True)
            if y > 47 and land[y][ox + 1]:
                lay_road(ox + 1, y, ROAD, vertical=True)
        for y in (10, 16, 23, 29, 37, 44, 50):
            bx = 129 if y <= 46 else 129 + (y - 46)
            for x in range(bx, 152):
                if land[y][x] and g[y][x] not in (SAND, SANDPALM):
                    lay_road(x, y, ROAD)

        # Four East-West Bridges across the bay (Prawn, Leaf Links, Starfish, South)
        for y in BRIDGE_ROWS:
            end_x = 133 if y == 50 else 129
            for x in range(60, end_x + 1):
                lay_road(x, y, ROAD)

        # Leaf Links vertical foot/cart bridges linking all 3 golf islands
        for y in range(18, 30):
            if g[y][98] in WATER:
                g[y][98] = BRIDGE
                self.vert.add((98, y))

        # Sprinkle palms on open grass
        for y in range(H):
            for x in range(W):
                if g[y][x] == GRASS and rnd.random() < 0.07:
                    g[y][x] = PALM

        self.signs = list(SIGNS)
        self.spawn = (145, 20)
        # (name, district, scene, x, y[, ghost_only]) - walk within 2 cells and press E
        self.landmarks = [
            ("Sunset Pier", "Neon Shores", scene_pier, 155, 29),
            ("Pink Flamingo Motel", "Neon Shores", scene_motel, 145, 13),
            ("Club 86 Rooftop", "Chrome Heights", scene_rooftop, 48, 10),
            ("Runway 86", "Vibe Int'l Airport", scene_runway, 26, 49),
            ("Crane Row", "Starlight Docks", scene_docks, 67, 48),
            ("Sunset Gas Stop", "Route 86", scene_gas_stop, 32, 27),
            ("Secret Fan Art", "Neon Shores", scene_fan_art, 137, 46, True),
        ]

    def near(self, x, y, ghost=False):
        for lm in self.landmarks:
            ghost_only = len(lm) > 5 and lm[5]
            if ghost_only and not ghost:
                continue
            dist = 1 if ghost_only else 2
            if max(abs(lm[3] - x), abs(lm[4] - y)) <= dist:
                return lm
        return None

    def look(self, x, y, now, day=0.0, lit=0.57):
        """(glyph, fg, bg) for a map cell at time `now`, tinted for daylight."""
        ch, fg, bg = self._look(x, y, now, lit)
        if day > 0:
            fg, bg = tint(fg, day), tint(bg, day)
        return ch, fg, bg

    def _look(self, x, y, now, lit_frac):
        t, h = self.g[y][x], self.h[y][x]
        if t == OCEAN:
            w = math.sin(x * 0.35 + y * 0.7 - now * 1.8) + 0.6 * math.sin(x * 0.11 - y * 0.2 + now * 0.9)
            if w > 1.1:
                return "~", 159, 25
            if w > 0.2:
                return "~", 39, 18
            return " ", 17, 18
        if t == BAY:
            return ("~", 44, 23) if math.sin(x * 0.5 + y * 0.9 - now * 1.1) > 0.55 else (" ", 23, 23)
        if t == CANAL:
            return ("~" if (x + int(now * 3)) % 3 == 0 else " "), 51, 30
        if t == SAND:
            return ("·" if h % 6 == 0 else " "), 137, 223
        if t == SANDPALM:
            return "♣", 28, 223
        if t == GRASS:
            return ('"' if h % 9 == 0 else " "), 71, 22
        if t == PALM:
            return "♣", 48, 22
        if t == ROAD:
            return " ", 0, 237
        if t == HWY:
            if (x, y) in self.hwy_v and (x, y) not in self.hwy_h:
                return ("│" if y % 2 == 0 else " "), 220, 237
            if (x, y) in self.hwy_h:
                return ("─" if x % 4 < 2 else " "), 220, 237
            return " ", 220, 237
        if t == BRIDGE:
            return ("║" if (x, y) in self.vert else "═"), 250, 238
        if t == TOWER:
            bg = TOWER_BG[((x // 9) * 7 + (y // 4) * 3) % len(TOWER_BG)]
            if x % 2:
                lit = (h + int(now / 4 + h % 13)) % 20 < lit_frac * 20
                return "▪", (WINDOW_FG[h % 3] if lit else 60), bg
            return " ", 0, bg
        if t == HOTEL:
            bg = HOTEL_BG[(y // 5) % len(HOTEL_BG)]
            if x % 2 == 0:
                lit = (h + int(now / 5 + h % 11)) % 20 < lit_frac * 17
                return "▪", (202 if lit else 24), bg
            return " ", 0, bg
        if t == HOUSE:
            return "⌂", HOUSE_FG[h % 4], 22
        if t == RUNWAY:
            if (x, y) in self.runway_dash:
                return "─", 255, 240
            if (x, y) in self.runway_edge:
                return "·", 226, 240
            return " ", 0, 240
        if t == TARMAC:
            return " ", 0, 238
        if t == DOCK:
            return ("·" if h % 7 == 0 else " "), 244, 236
        if t == CONTAINER:
            return "▆", CONTAINER_FG[(x // 3 + y) % len(CONTAINER_FG)], 236
        return "?", 196, 0

    def district(self, x, y):
        t = self.g[y][x]
        if t == OCEAN:
            return "The Big Blue"
        if t == BRIDGE:
            if y == 37:
                return "Vibe Causeway"
            if y == 50:
                return "Starlight Channel"
            return "Vibe Bay"
        if t == BAY:
            return "Starlight Channel" if y >= 48 else "Vibe Bay"
        if x >= 120:
            return "Neon Shores"
        if x >= 78:
            return "Flamingo Keys"
        if t == HWY:
            if x in (40, 41) and y not in (27, 37):
                return "I-Vibe Expressway"
            return "Route 86"
        if y < 16:
            return "Chrome Heights"
        if y < 27:
            return "Palmetto Downs"
        if y < 38:
            return "Mango Gardens"
        if x >= 43:
            return "Starlight Docks"
        return "Mango Gardens" if y < 43 else "Vibe Int'l Airport"


DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]
CAR_GLYPH = ["▶", "▼", "◀", "▲"]


class Car:
    __slots__ = ("x", "y", "d", "fg")

    def __init__(self, x, y, d, fg):
        self.x, self.y, self.d, self.fg = x, y, d, fg


def spawn_cars(world, n, rnd):
    roads = [(x, y) for y in range(H) for x in range(W) if world.g[y][x] in ROADISH]
    return [Car(*rnd.choice(roads), rnd.randrange(4), rnd.choice(CAR_FG)) for _ in range(n)]


def step_car(world, c, rnd):
    opts = []
    for i, (dx, dy) in enumerate(DIRS):
        if i == (c.d + 2) % 4:
            continue
        nx, ny = c.x + dx, c.y + dy
        if 0 <= nx < W and 0 <= ny < H and world.g[ny][nx] in ROADISH:
            opts.append(i)
    if not opts:
        c.d = (c.d + 2) % 4
        return
    c.d = c.d if c.d in opts and (len(opts) == 1 or rnd.random() < 0.8) else rnd.choice(opts)
    c.x += DIRS[c.d][0]
    c.y += DIRS[c.d][1]


# --------------------------------------------------------------------------- title screen

FONT = {
    "V": ["█   █", "█   █", "█   █", " █ █ ", "  █  "],
    "I": ["███", " █ ", " █ ", " █ ", "███"],
    "B": ["████ ", "█   █", "████ ", "█   █", "████ "],
    "E": ["████", "█   ", "███ ", "█   ", "████"],
    "C": [" ███", "█   ", "█   ", "█   ", " ███"],
    "T": ["█████", "  █  ", "  █  ", "  █  ", "  █  "],
    "Y": ["█   █", " █ █ ", "  █  ", "  █  ", "  █  "],
    " ": ["  ", "  ", "  ", "  ", "  "],
}
TITLE_FG = [219, 213, 207, 201, 199]
SKY = [17, 17, 54, 54, 91, 127, 163, 169, 205, 211, 217]
SUN = [226, 220, 214, 208, 203, 198]
PALM_ART = [
    r" \\ | // ",
    r"==\\|//==",
    r" //||\\  ",
    r"    ||   ",
    r"    ||   ",
    r"   ||    ",
    r"   ||    ",
    r"  ||     ",
]


def big_text(text):
    rows = [""] * 5
    for ch in text:
        for i in range(5):
            rows[i] += FONT[ch][i] + " "
    return rows


def put(grid, x, y, text, fg, bold=False, bg=None):
    if not 0 <= y < len(grid):
        return
    row = grid[y]
    for i, ch in enumerate(text):
        if 0 <= x + i < len(row):
            row[x + i] = (ch, fg, row[x + i][2] if bg is None else bg, bold)


def splash_frame(rows, cols, now):
    grid = [[(" ", 0, 16, False)] * cols for _ in range(rows)]
    hy = int(rows * 0.62)
    for y in range(hy):
        bg = SKY[min(len(SKY) - 1, y * len(SKY) // max(1, hy))]
        for x in range(cols):
            star = y < hy * 0.45 and (x * 7919 + y * 104729) % 61 == 0
            twinkle = star and (x + y + int(now * 3)) % 5 == 0
            grid[y][x] = (("·" if not twinkle else "*") if star else " ", 255, bg, twinkle)
    # striped synthwave sun sitting on the horizon
    cx, r = cols // 2, max(3, int(hy * 0.42))
    for y in range(hy - r, hy):
        if y < 0:
            continue
        frac = (y - (hy - r)) / r
        if frac > 0.4 and (y + int(now * 3)) % 3 == 0:
            continue
        half = int(2 * r * math.sqrt(max(0.0, 1 - ((hy - y) / r) ** 2)))
        for x in range(max(0, cx - half), min(cols, cx + half + 1)):
            grid[y][x] = (" ", 0, SUN[min(5, int(frac * 6))], False)
    # perspective grid floor
    for y in range(hy, rows):
        d = y - hy + 1
        z1, z0 = 8.0 / d + now * 1.5, 8.0 / (d + 1) + now * 1.5
        horiz = d >= 2 and int(z0) != int(z1)
        for x in range(cols):
            grid[y][x] = ("─" if horiz else " ", 201, 17, False)
        for i in range(-24, 25):
            x = int(cx + i * (2 + d * 1.6))
            if 0 <= x < cols:
                grid[y][x] = ("│" if i == 0 else ("╱" if i < 0 else "╲"), 165, 17, False)
    # palm silhouettes
    for px in (int(cols * 0.08), int(cols * 0.80)):
        for i, line in enumerate(PALM_ART):
            y = hy - len(PALM_ART) + i
            for j, ch in enumerate(line):
                if ch != " " and 0 <= y < rows and 0 <= px + j < cols:
                    grid[y][px + j] = (ch, 16, grid[y][px + j][2], True)
    # title
    ty = max(1, int(hy * 0.12))
    wide, narrow = big_text("VIBE CITY"), big_text("VIBE") + [""] + big_text("CITY")
    if len(wide[0]) + 2 <= cols and ty + 6 < hy:
        title = wide
    elif len(narrow[0]) + 2 <= cols and ty + 12 < hy:
        title = narrow  # stack the words on narrow terminals
    else:
        title = None
    if title:
        tx = (cols - len(title[0])) // 2
        for i, line in enumerate(title):
            for j, ch in enumerate(line):
                if ch != " ":
                    put(grid, tx + j + 1, ty + i + 1, "█", 51)
        for i, line in enumerate(title):
            for j, ch in enumerate(line):
                if ch != " ":
                    put(grid, tx + j, ty + i, "█", TITLE_FG[i % 6 % 5], True)
        sub_y = ty + len(title) + 2
    else:
        t = "V I B E   C I T Y"
        put(grid, (cols - len(t)) // 2, ty, t, 201, True)
        sub_y = ty + 2
    sub = "★  A NEON TRIBUTE TO THE GTA VI LAUNCH  ★"
    if len(sub) > cols:
        sub = "★ GTA VI LAUNCH TRIBUTE ★"
    put(grid, max(0, (cols - len(sub)) // 2), sub_y, sub, 229, True)
    if int(now * 2) % 2 == 0:
        p = "[ press any key to cruise ]"
        put(grid, (cols - len(p)) // 2, rows - 3, p, 51, True)
    note = "fan-made · original map & names · not affiliated with Rockstar Games"
    if len(note) >= cols:
        note = "fan-made · not affiliated with Rockstar"
    put(grid, max(0, (cols - len(note)) // 2), rows - 1, note[:cols - 1], 245)
    return grid


def splash(scr, pal, ascii_mode):
    t0 = time.time()
    while True:
        k = scr.getch()
        if k in (ord("q"), ord("Q")):
            return False
        if k not in (-1, curses.KEY_RESIZE):
            return True
        if k == curses.KEY_RESIZE:
            scr.erase()
        rows, cols = scr.getmaxyx()
        flush(scr, pal, splash_frame(rows, cols, time.time() - t0), 0, ascii_mode)
        scr.refresh()
        curses.napms(50)


# --------------------------------------------------------------------------- landmark scenes

def ihash(x, y, s=0):
    return ((x * 73856093) ^ (y * 19349663) ^ (s * 83492791)) & 0x7FFFFFFF


def canvas(rows, cols, bg=16):
    return [[(" ", 0, bg, False)] * cols for _ in range(rows)]


def cell(g, x, y, ch, fg, bg=None, bold=False):
    if 0 <= y < len(g) and 0 <= x < len(g[0]):
        g[y][x] = (ch, fg, g[y][x][2] if bg is None else bg, bold)


def fill(g, x0, y0, x1, y1, bg, ch=" ", fg=0):
    for y in range(max(0, y0), min(len(g), y1)):
        row = g[y]
        for x in range(max(0, x0), min(len(row), x1)):
            row[x] = (ch, fg, bg, False)


def sky(g, y0, y1, colors):
    for y in range(max(0, y0), min(len(g), y1)):
        fill(g, 0, y, len(g[0]), y + 1,
             colors[min(len(colors) - 1, (y - y0) * len(colors) // max(1, y1 - y0))])


def stars(g, y1, now, every=53):
    for y in range(min(y1, len(g))):
        for x in range(len(g[0])):
            hsh = ihash(x, y)
            if hsh % every == 0:
                tw = (hsh // every + int(now * 3)) % 6 == 0
                cell(g, x, y, "*" if tw else "·", 255, None, tw)


def art(g, x, y, lines, fg, bold=True):
    for i, line in enumerate(lines):
        for j, ch in enumerate(line):
            if ch != " ":
                cell(g, x + j, y + i, ch, fg, None, bold)


def disc(g, cx, cy, r, bg):
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - 2 * r, cx + 2 * r + 1):
            if ((x - cx) / (2 * r)) ** 2 + ((y - cy) / r) ** 2 <= 1:
                cell(g, x, y, " ", 0, bg)


def sun(g, cx, hy, r, now):
    for y in range(hy - r, hy):
        frac = (y - (hy - r)) / r
        if frac > 0.4 and (y + int(now * 3)) % 3 == 0:
            continue
        half = int(2 * r * math.sqrt(max(0.0, 1 - ((hy - y) / r) ** 2)))
        for x in range(cx - half, cx + half + 1):
            cell(g, x, y, " ", 0, SUN[min(5, int(frac * 6))])


def chase_border(g, x0, y0, x1, y1, now, colors=(201, 51, 226, 46)):
    pts = ([(x, y0) for x in range(x0, x1 + 1)] + [(x1, y) for y in range(y0 + 1, y1 + 1)]
           + [(x, y1) for x in range(x1 - 1, x0 - 1, -1)] + [(x0, y) for y in range(y1 - 1, y0, -1)])
    for n, (x, y) in enumerate(pts):
        cell(g, x, y, "●", colors[(n + int(now * 8)) % len(colors)], None, True)


def lit_windows(g, x0, y0, x1, y1, now):
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            hsh = ihash(x, y)
            lit = (hsh + int(now / 3 + hsh % 7)) % 5 < 3
            cell(g, x, y, "▪", WINDOW_FG[hsh % 3] if lit else 60)


BOAT = ["   |\\   ", "   | \\  ", "   |__\\ ", " \\_____/"]


def scene_pier(rows, cols, now):
    g = canvas(rows, cols)
    hy = int(rows * 0.55)
    sky(g, 0, hy, [54, 91, 127, 163, 169, 205, 209, 215, 216, 222])
    stars(g, hy // 4, now)
    cx, r = int(cols * 0.62), max(3, int(hy * 0.42))
    sun(g, cx, hy, r, now)
    sea = [31, 24, 24, 23, 18, 18, 17]
    for y in range(hy, rows):
        d = y - hy
        bg = sea[min(len(sea) - 1, d * len(sea) // max(1, rows - hy))]
        half = int(r * 0.6 + d * 1.5)
        for x in range(cols):
            hsh = ihash(x, y, int(now * 4))
            if abs(x - cx) <= half and hsh % 3 == 0:
                g[y][x] = ("─", 220 if hsh % 2 else 209, bg, False)  # sun glitter
            elif hsh % 23 == 0:
                g[y][x] = ("~", 38, bg, False)
            else:
                g[y][x] = (" ", 0, bg, False)
    art(g, int((now * 3) % (cols + 30)) - 15, hy - 3, BOAT, 16)
    for i in range(3):  # gulls
        gx = cols - int((now * 4 + i * 23) % (cols + 10))
        gy = int(hy * 0.35 + i * 2 + math.sin(now * 2 + i) * 1.5)
        cell(g, gx, gy, "v" if int(now * 4 + i) % 2 else "-", 16, None, True)
    py, px1 = hy + 2, int(cols * 0.45)  # the pier itself
    fill(g, 0, py, px1, py + 1, 94)
    for x in range(px1):
        cell(g, x, py - 1, "┼" if x % 4 == 0 else "─", 180)
        if x % 4 == 1:
            for y in range(py + 1, min(rows, py + 5)):
                cell(g, x, y, "║", 58)
    for lx in range(6, px1 - 2, 12):
        for y in range(py - 4, py - 1):
            cell(g, lx, y, "│", 240)
        on = math.sin(now * 5 + lx) < 0.95
        cell(g, lx, py - 5, "●", 229 if on else 238, None, on)
    art(g, int(cols * 0.03), py - 1 - len(PALM_ART), PALM_ART, 16)
    return g


def scene_rooftop(rows, cols, now):
    g = canvas(rows, cols)
    ground = rows - 5
    sky(g, 0, ground, [16, 16, 17, 17, 18, 54, 55, 91])
    stars(g, ground // 2, now)
    for k, bx in enumerate((int(cols * 0.22), int(cols * 0.7))):  # searchlights
        a = 0.6 * math.sin(now * 0.6 + k * 2.1)
        for t in range(1, rows * 3):
            x0, y = bx + math.sin(a) * t, int(ground - math.cos(a) * t * 0.5)
            if y < 0:
                break
            w = 1 + t // 12
            for dx in range(-w, w + 1):
                cell(g, int(x0) + dx, y, " ", 0, 60 if abs(dx) < w else 59)
    disc(g, int(cols * 0.85), max(2, int(rows * 0.12)), 2, 230)
    rnd = random.Random(7)
    x = i = 0
    while x < cols:  # skyline
        w = rnd.randint(6, 14)
        top = ground - rnd.randint(int(ground * 0.25), int(ground * 0.75))
        fill(g, x, top, x + w - 1, ground, TOWER_BG[i % len(TOWER_BG)])
        lit_windows(g, x + 1, top + 1, x + w - 2, ground, now)
        if rnd.random() < 0.45:
            ax = x + w // 2
            cell(g, ax, top - 1, "│", 240)
            cell(g, ax, top - 2, "│", 240)
            cell(g, ax, top - 3, "●", 196 if int(now * 2 + i) % 2 else 52, None, True)
        x, i = x + w, i + 1
    cw = min(22, cols - 4)  # the club tower and its sign
    cx0, ctop = (cols - cw) // 2, int(ground * 0.4)
    fill(g, cx0, ctop, cx0 + cw, ground, 53)
    lit_windows(g, cx0 + 1, ctop + 1, cx0 + cw - 1, ground, now)
    fill(g, cx0, ctop - 5, cx0 + cw, ctop, 16)
    chase_border(g, cx0, ctop - 5, cx0 + cw - 1, ctop - 1, now)
    if math.sin(now * 6) < 0.93:
        put(g, cx0 + (cw - 7) // 2, ctop - 3, "CLUB 86", [201, 51, 226, 46][int(now * 1.5) % 4], True)
    hx, hy = cols + 10 - int(now * 7 % (cols + 30)), 2 + int(math.sin(now) + 1)  # helicopter
    put(g, hx, hy, "-----+-----" if int(now * 12) % 2 else "    -+-    ", 245)
    put(g, hx + 3, hy + 1, "<[##]==-", 245, True)
    cell(g, hx + 11, hy + 1, "●", 196 if int(now * 3) % 2 else 16, None, True)
    for xx in range(cols):  # rooftop railing + dance floor
        cell(g, xx, ground, "┬" if xx % 3 == 0 else "─", 250, 236)
    tiles = [162, 37, 178, 35, 98]
    for yy in range(ground + 1, rows):
        for xx in range(cols):
            g[yy][xx] = (" ", 0, tiles[(xx // 4 + yy + int(now * 3)) % 5], False)
    return g


FLAMINGO = [" _    ", "(o>   ", " ||   ", " \\\\___", "  \\__/", "   || ", "   || "]
CAR_ART = ["    ____    ", " __/__|_\\__ ", "|  _    _  |", "'-(_)--(_)-'"]
NEON_FG = {213, 51, 196, 46, 229, 201, 226}


def scene_motel(rows, cols, now):
    g = canvas(rows, cols)
    gy = int(rows * 0.72)
    sky(g, 0, gy, [16, 17, 17, 18, 54, 55, 91, 90])
    stars(g, gy // 2, now)
    fill(g, 0, gy, cols, rows, 236)  # parking lot
    for x in range(4, cols, 12):
        for y in range(gy + 2, min(rows - 1, gy + 5)):
            cell(g, x, y, "│", 250)
    bx0, bx1 = int(cols * 0.04), int(cols * 0.64)
    top = int(rows * 0.3)
    mid = (top + gy) // 2
    fill(g, bx0 - 1, top - 1, bx1 + 1, top, 168)
    fill(g, bx0, top, bx1, gy, 218)
    for x in range(bx0, bx1):
        cell(g, x, mid, "┼" if (x - bx0) % 4 == 0 else "─", 255)
    n = 1
    for floor_top, floor_bot in ((top + 1, mid), (mid + 1, gy)):
        for ux in range(bx0 + 2, bx1 - 7, 9):
            fill(g, ux, floor_bot - 3, ux + 2, floor_bot, 30)
            lit = ihash(ux, floor_top, int(now / 4)) % 3 > 0
            fill(g, ux + 3, floor_bot - 3, ux + 7, floor_bot - 1, 229 if lit else 60)
            if floor_bot - 4 > floor_top:
                put(g, ux, floor_bot - 4, str(n), 89, True)
            n += 1
    art(g, int(cols * 0.66), gy - len(PALM_ART), PALM_ART, 28)
    sw, sh = 19, 7  # the big sign
    sx0, sy0 = min(cols - sw - 1, int(cols * 0.72)), max(1, int(rows * 0.1))
    pole = sx0 + sw // 2
    for y in range(sy0 + sh, gy):
        cell(g, pole, y, "║", 245)
    fill(g, sx0, sy0, sx0 + sw, sy0 + sh, 16)
    chase_border(g, sx0, sy0, sx0 + sw - 1, sy0 + sh - 1, now)
    if math.sin(now * 5) < 0.93:
        put(g, sx0 + 3, sy0 + 1, "PINK FLAMINGO", 213, True)
    put(g, sx0 + 5, sy0 + 2, "~ MOTEL ~", 51, True)
    put(g, sx0 + 4, sy0 + 4, "NO" if int(now * 1.3) % 5 == 0 else "  ", 196, True)
    put(g, sx0 + 7, sy0 + 4, "VACANCY", 46, True)
    put(g, sx0 + 3, sy0 + 5, "COLOR TV  POOL", 229)
    for y in range(gy + 1, rows - 1):  # neon reflections on wet asphalt
        my = gy - (y - gy)
        if my < 0:
            break
        for x in range(cols):
            ch, fg, bg, _ = g[my][x]
            if ((ch != " " and fg in NEON_FG) or bg == 229) and ihash(x, y, int(now * 6)) % 3 == 0:
                cell(g, x, y, "░", fg if ch != " " else 229)
    art(g, pole - 9, rows - 1 - len(FLAMINGO), FLAMINGO, 205)
    art(g, int(cols * 0.3), rows - 1 - len(CAR_ART), CAR_ART, 51)
    return g


PLANE_BIG = ["              |              ", "    __________|__________    ",
             " ---o----o---(_)---o----o--- ", "              |              ",
             "           ---+---           "]
PLANE_MED = ["      |      ", " _____|_____ ", "-o--o(_)o--o-", "     -+-     "]
PLANE_SMALL = ["   |   ", "-o(_)o-"]


def scene_runway(rows, cols, now):
    g = canvas(rows, cols)
    hy = int(rows * 0.42)
    sky(g, 0, hy, [17, 54, 91, 127, 168, 174, 180, 216])
    stars(g, hy // 4, now)
    rnd = random.Random(3)
    x = 0
    while x < cols:  # far-off skyline
        w, h = rnd.randint(2, 6), rnd.randint(1, 4)
        fill(g, x, hy - h, x + w, hy, rnd.choice([53, 54, 60]))
        if h > 1 and rnd.random() < 0.6:
            cell(g, x + rnd.randrange(w), hy - h + 1, "·", 229)
        x += w + rnd.randint(0, 2)
    cx, depth = cols // 2, max(1, rows - hy)
    for y in range(hy, rows):  # runway in perspective, lights rushing past
        d = y - hy + 1
        half = int(d * cols * 0.3 / depth)
        fill(g, 0, y, cols, y + 1, 22)
        fill(g, cx - half, y, cx + half + 1, y + 1, 238)
        z1, z0 = 10.0 / d + now * 2.5, 10.0 / (d + 1) + now * 2.5
        if d >= 2 and int(z0) != int(z1):
            c = 226 if int(z1) % 2 else 51
            cell(g, cx - half - 1, y, "●", c, None, True)
            cell(g, cx + half + 1, y, "●", c, None, True)
            w = half // 14
            fill(g, cx - w, y, cx + w + 1, y + 1, 252)
    p = (now % 7.0) / 7.0  # a jet takes off every 7 seconds
    plane = PLANE_BIG if p < 0.35 else PLANE_MED if p < 0.7 else PLANE_SMALL
    y0, y1 = rows - 2 - len(PLANE_BIG), hy - 4
    py, px = int(y0 + (y1 - y0) * p), cx - len(plane[0]) // 2
    art(g, px, py, plane, 255)
    if int(now * 3) % 2:
        wing = next(i for i, l in enumerate(plane) if "o" in l)
        line = plane[wing]
        cell(g, px + len(line) - len(line.lstrip()), py + wing, "●", 196, None, True)
        cell(g, px + len(line.rstrip()) - 1, py + wing, "●", 46, None, True)
    return g


SHIP = ["        ▄▄      ", "   ▄▄▄▄▄██▄▄▄   ", " ▀████████████▀ "]


def scene_docks(rows, cols, now):
    g = canvas(rows, cols)
    wy = int(rows * 0.7)
    dock = wy - 2
    sky(g, 0, dock, [16, 16, 17, 17, 18, 18, 24])
    stars(g, dock // 2, now)
    lx, ltop = cols - 8, int(rows * 0.3)
    a = now * 0.9  # lighthouse beam sweeping
    dirn = -1 if math.sin(a) > 0 else 1
    for t in range(1, int(abs(math.cos(a)) * cols * 0.7)):
        spread = t // 10
        for yy in range(ltop - 1 - spread, ltop + spread):
            cell(g, lx + 1 + dirn * t, yy, " ", 0, 60 if abs(yy - (ltop - 1)) <= spread // 2 else 59)
    mx, my = int(cols * 0.2), max(3, int(rows * 0.15))
    disc(g, mx, my, 3, 230)
    for dx, dy in ((-2, -1), (3, 1), (0, 2)):
        cell(g, mx + dx, my + dy, "·", 187)
    for y in range(wy, rows):  # water + moon path
        for x in range(cols):
            hsh = ihash(x, y, int(now * 3))
            if abs(x - mx) <= 2 + (y - wy) and hsh % 3 == 0:
                g[y][x] = ("─", 230, 17, False)
            elif hsh % 19 == 0:
                g[y][x] = ("~", 24, 17, False)
            else:
                g[y][x] = (" ", 0, 17, False)
    for k, cx0 in enumerate((int(cols * 0.32), int(cols * 0.56))):  # gantry cranes
        top = max(2, int(rows * 0.18))
        for y in range(top + 1, dock):
            cell(g, cx0, y, "║", 240)
            cell(g, cx0 + 3, y, "║", 240)
            a1, a2 = ("╲", "╱") if y % 2 else ("╱", "╲")
            cell(g, cx0 + 1, y, a1, 238)
            cell(g, cx0 + 2, y, a2, 238)
        for x in range(cx0 - 8, cx0 + 23):
            cell(g, x, top, "═", 242)
        fill(g, cx0 - 8, top + 1, cx0 - 4, top + 3, 238)
        fill(g, cx0, top + 1, cx0 + 4, top + 3, 136)
        cell(g, cx0 + 1, top + 1, "▪", 229)
        cell(g, cx0 + 22, top - 1, "●", 196 if int(now * 1.5 + k) % 2 else 52, None, True)
        tx = cx0 + 7 + int((math.sin(now * 0.4 + k * 2) + 1) / 2 * 13)
        hd = top + 2 + int((math.sin(now * 0.7 + k) + 1) / 2 * max(1, dock - top - 6))
        for y in range(top + 1, hd):
            cell(g, tx, y, "│", 245)
        fill(g, tx - 3, hd, tx + 4, hd + 1, [124, 24][k])
    fill(g, 0, dock, cols, wy, 239)  # quay + container stacks
    rnd = random.Random(5)
    x = 1
    while x < lx - 7:
        for j in range(rnd.randint(0, 4)):
            y = dock - 1 - j
            fill(g, x, y, x + 6, y + 1, rnd.choice([124, 166, 24, 28, 90, 136]))
            cell(g, x + 2, y, "│", 16)
            cell(g, x + 4, y, "│", 16)
        x += 7
    for y in range(ltop, dock):  # lighthouse
        fill(g, lx, y, lx + 3, y + 1, 196 if (y // 2) % 2 else 255)
    fill(g, lx, ltop - 1, lx + 3, ltop, 229)
    cell(g, lx + 1, ltop - 2, "▲", 160, None, True)
    sx = cols + 5 - int(now * 2 % (cols + 30))  # cargo ship
    art(g, sx, wy, SHIP, 237)
    for j in range(4):
        cell(g, sx + 4 + j * 2, wy + 2, "·", 229)
    return g


def palm(g, bx, by, height, lean, fg):
    """A procedural palm silhouette: curved trunk plus drooping fronds."""
    tx, ty = bx, by
    for i in range(height):
        tx = bx + int(lean * (i / max(1, height)) ** 2 * height * 0.6)
        ty = by - i
        cell(g, tx, ty, "│" if i % 3 else "┃", fg, None, True)
    flen = max(4, int(height * 0.9))
    for dirx in (-1, 1):
        for rise in (0.7, 0.3, -0.05, -0.4):
            prev_y = ty
            for s in range(1, flen):
                y = int(round(ty - rise * s * 0.5 + 0.35 * flen * (s / flen) ** 2))
                slope = y - prev_y
                if slope == 0:
                    ch = "─"
                elif (slope > 0) == (dirx > 0):
                    ch = "╲"
                else:
                    ch = "╱"
                cell(g, tx + dirx * s, y, ch, fg, None, True)
                prev_y = y
    for dx in (-1, 0, 1):
        cell(g, tx + dx, ty + 1, "●", fg, None, True)  # coconuts


MUSCLE_CAR = [
    "            _______________           ",
    "       ____/  _____|_____  \\____      ",
    "   ___/   /__/_____|_____\\__\\   `--._ ",
    "  |   _                        _     |",
    "  |__(_)______________________(_)____|",
    "      `-'                      `-'    ",
]

GAS_DUO_PAL = {
    "H": 234, "N": 17,  "R": 125, "r": 88,  "S": 216, "s": 173, "L": 223,
    "P": 94,  "p": 137, "G": 250, "M": 244, "g": 60,  "B": 103,
}

GAS_DUO = [
    "...................................H................",
    ".................................HHHHH..............",
    "................................gHHHHHM.............",
    "................................gHHHHHp.............",
    "................................MspppGG.............",
    "................................pGsspGG.............",
    "................HHg.........ppppsgPpPMGGpps.........",
    "..............HHHHHg.......pppMpGpMMMpGggps.........",
    ".............HPHHgMgg......ppppNNNNNNNNNNppp........",
    "............GppPHHHgg.....ppppMNNNNNNNNNMppgM.......",
    "............GpPppHHgH....pppM..NNNNNNNNGgMggpG......",
    "............MgPpLMPMHg..spppg..NNNNNNNMG..HpppG.....",
    "............RRRRSLRrHgMppppggHggNNNNNNgBgBBppppG....",
    "............SrRRRRRHHgpppspgHHNNNNNNNNNNNgHHppppL...",
    "............SRrrRRSHgMppppgHHHNgNNNNNNNNgggHgppppL..",
    "...........gSRrRRSRrMpppppHHHHNggNNNNNgNggHHgppppp..",
    "...........gRRRrRRrrRppppPHHHHggggNNNgggggHHHgppppL.",
    "..........MrRRRRRRRRMGGMMMHHHHggggNNggggggHHHgpppppG",
    "..........MRGRRRRRMMMMGGsMHHHHggggggggggggHHHgpppppG",
    ".........GGMMRRrRRMMMMMMMGHHHHggBgggggggggHHHgppppg.",
    ".......GGMMMMMSRrMMMMMMMMGMHHggggHggHHgggggHHHggpg..",
    "......GGMMMGGMMMMMMMMMMMMGLgHggggHgggggggHgg........",
    ".....GsMMMMGGMMMMMMMMMMMMMG.gH.ggHgggggggHBL........",
    "...GsssMMMMMMMMMMMMMMMMMMMG.gH.ggHgggggggHLL........",
    "..GGssMMMHHMMMMMMMMMMMMHMMs.gH..gggggggBgHL.........",
    ".GGGGGGss..MMMMMMMMMMMMMMssG.Hg.gggggBgggHGG........",
    ".ssGGGGGGGMMMMMMMMMMMMMMMssG.Hg..ggBBggggHGG........",
    "..ssssMMMMMsMMMMMMMMMMM.MssGBggBBgggggggggGG........",
    "..........MsssMMMMMMMMG.MsssB.g...HgggggggBL........",
    "...........MsMsMMMMMMMG..MspG....ggggggggggG........",
    "...........MMMMMMMMMMMG..MMpp...HgggHHHHgBBG........",
    "............MMHMMMMMMMM...Mpsg.HggggggHHHHH.........",
    "............GMMMMMsssss...Mpsggg..ggHHHHHHH.........",
    "............GBMggMppppL...pssgg..gHHHHHHHHH.........",
    "...........GGBMgMgppMMB...GpsggggHHHHHHHHHH.........",
    "..........GGBggggggMggMG..GpGBggHHHHHHgggHH.........",
    "..........GBMgMggggggggG..GppppPHHHHHPPPPPP.........",
    ".........GGBBBgMMggMgggG..sspppPHHHPHPPPPPP.........",
    ".........GGMMBBBBgBMgggBGGpppPPPPPHHHPPPPPp.........",
    ".........GBBggggggMMMMMMGppLpPPPPPPHHHPPPPp.........",
    ".........BMgggggggMMMMMMGp.pppPPPPPHHPPPPPs.........",
    ".........GBBgggggggggggMpp..pppPPPHHHHPPPPp.........",
    ".........GBMMMMggggggggMMM..pppPPHHHPPPPPP..........",
    ".........psppppMggg....MM...ppPPPPHHPPPPPP..........",
    ".........GGsppppMgggM.......pppPPPHHPPPPPp..........",
    "..........GspppppggMpppp....pppPPPHPPPPPPp..........",
    "..........GspppppMgppppp....pppPPHHPPPPPP...........",
    "..........GGpppppMgppppp.....ppPPHHPpPPPP...........",
    "..........GGpppppMgppppp.....ppPPPHppPPPp...........",
    "...........GpppppMgppppp.....ppPPPHpppPPL...........",
    "...........GpppppMgppppp.....ppPPPHpppPpL...........",
    "...........GpppppM.Mpppp.....ppPPPHppPPpL...........",
    "...........BGMpppM.Mpppp.....pppPPHppPPpL...........",
    "............GMpppM.gpppp......ppPPHppPPpL...........",
    "............BMpppp.Mpppp......ppPPHppPPPL...........",
    ".............pppps.Bpppp......pPPPHpPPPPp...........",
    ".............GpppL..pppp.......PPHPpPPPPp...........",
    ".............GpppS..Gppp.......pHHPpPPPPL...........",
    ".............GpppS..sppp.......pPHPpPPPP............",
    ".............GpppS..pppMG......ppHPpPPPp............",
]


def draw_gas_duo(g, rows, cols, now):
    sh, sw = len(GAS_DUO), len(GAS_DUO[0])
    target_rows = min(sh // 2, max(10, int(rows * 0.72)))
    target_cols = max(14, int(round(target_rows * 2 * sw / sh)))
    x0 = max(1, (cols - target_cols) // 2 + int(cols * 0.08))
    y0 = max(1, rows - 1 - target_rows)
    glint = int(now * 2.5) % 6 == 0
    for ry in range(target_rows):
        sy_top = min(sh - 1, int((ry * 2) * sh / (target_rows * 2)))
        sy_bot = min(sh - 1, int((ry * 2 + 1) * sh / (target_rows * 2)))
        gy = y0 + ry
        if not (0 <= gy < rows):
            continue
        for rx in range(target_cols):
            sx = min(sw - 1, int(rx * sw / target_cols))
            gx = x0 + rx
            if not (0 <= gx < cols):
                continue
            tc, bc = GAS_DUO[sy_top][sx], GAS_DUO[sy_bot][sx]
            if tc == "." and bc == ".":
                continue
            tcol = GAS_DUO_PAL.get(tc)
            bcol = GAS_DUO_PAL.get(bc)
            if glint and tc == "L":
                tcol = 230
            if glint and bc == "L":
                bcol = 230
            if tcol is not None and bcol is not None:
                if tcol == bcol:
                    cell(g, gx, gy, " ", 0, tcol)
                else:
                    cell(g, gx, gy, "▀", tcol, bcol)
            elif tcol is not None:
                cell(g, gx, gy, "▀", tcol, g[gy][gx][2])
            else:
                cell(g, gx, gy, "▄", bcol, g[gy][gx][2])


def scene_gas_stop(rows, cols, now):
    g = canvas(rows, cols)
    hy = int(rows * 0.68)  # where the ground starts
    sky(g, 0, hy, [54, 55, 61, 97, 133, 169, 175, 211, 217, 224])
    stars(g, hy // 5, now, every=71)
    for k, (fy, fx, ln) in enumerate(((0.22, 0.15, 30), (0.30, 0.55, 40), (0.38, 0.05, 22), (0.44, 0.70, 26))):
        y, x0 = int(hy * fy), int(cols * fx + now * (0.4 + 0.2 * k)) % (cols + ln) - ln
        for i in range(ln):  # thin pink cloud streaks drifting
            if ihash(i, k) % 5:
                cell(g, x0 + i, y, "─", 218 if k % 2 else 225)
    px, py = int((now * 5) % (cols + 60)) - 20, max(2, int(hy * 0.16))  # plane + contrail
    for i in range(2, 60):
        if ihash(i, int(now)) % (2 + i // 15) == 0:
            cell(g, px - i, py + 1 + i // 14, "·", 231)
    put(g, px, py, " _/\\_", 60, True)
    put(g, px, py + 1, "<____>", 60, True)
    for fx, fh, lean in ((0.10, 7, 1), (0.27, 6, -1), (0.50, 8, 1), (0.60, 5, 0), (0.78, 7, -1)):
        palm(g, int(cols * fx), hy - 1, max(3, int(fh * rows / 45)), lean, 140)  # far palms, hazy
    for y in range(hy, rows):  # asphalt, purple-tinted by the sunset
        bg = [146, 103, 60, 59, 238, 237][min(5, (y - hy) * 6 // max(1, rows - hy))]
        fill(g, 0, y, cols, y + 1, bg)
    for x in range(0, cols, 8):
        cell(g, x + int(now * 0) % 8, hy + max(2, (rows - hy) // 3), "▬", 223)
    poles = [int(cols * f) for f in (0.03, 0.19, 0.35)]  # power line with birds
    ptop = max(2, hy - int(rows * 0.36))
    for p in poles:
        for y in range(ptop, hy):
            cell(g, p, y, "│", 54, None, True)
        put(g, p - 2, ptop, "─┼─┼─", 54, True)
    for a, b in zip(poles, poles[1:]):
        for wire, sag in ((0, 3), (1, 4)):
            for x in range(a + 1, b):
                t = (x - a) / (b - a)
                y = ptop + wire + int(round(sag * 4 * t * (1 - t)))
                cell(g, x, y, "─", 54)
                if wire == 0 and ihash(x, 7) % 9 == 0:
                    cell(g, x, y - 1, "v" if int(now * 2 + x) % 7 == 0 else "•", 16, None, True)
    sx0, sx1 = int(cols * 0.62), int(cols * 0.96)  # shop behind the canopy
    fill(g, sx0, hy - 6, sx1, hy, 103)
    for x in range(sx0 + 2, sx1 - 2, 4):
        fill(g, x, hy - 4, x + 3, hy - 2, 222 if ihash(x, int(now / 4)) % 4 else 180)
    fill(g, sx1 - 6, hy - 4, sx1 - 3, hy, 60)
    if math.sin(now * 5) < 0.93:
        put(g, sx0 + (sx1 - sx0 - 10) // 2, hy - 7, " VIBE GAS ", 213, True, 16)
    cx0, cx1 = int(cols * 0.44), int(cols * 0.84)  # canopy, pillars, pumps
    ctop = hy - int(rows * 0.2)
    fill(g, cx0, ctop, cx1, ctop + 1, 189)
    fill(g, cx0, ctop + 1, cx1, ctop + 2, 222)
    fill(g, cx0 + 1, ctop + 2, cx1 - 1, ctop + 3, 60)
    for x in (cx0 + 3, cx1 - 4):
        for y in range(ctop + 3, hy):
            cell(g, x, y, "║", 189, None, True)
    for k, x in enumerate(range(cx0 + 8, cx1 - 6, max(8, (cx1 - cx0) // 4))):
        fill(g, x, hy - 3, x + 3, hy, 167)
        cell(g, x + 1, hy - 3, "▪", 51 if int(now * 2 + k) % 3 else 46, None, True)
        cell(g, x + 3, hy - 2, "╮", 250)
    pole_x, pt = int(cols * 0.40), max(1, hy - int(rows * 0.42))  # neon price sign
    for y in range(pt + 5, hy):
        cell(g, pole_x, y, "║", 250, None, True)
    fill(g, pole_x - 6, pt, pole_x + 7, pt + 5, 16)
    chase_border(g, pole_x - 6, pt, pole_x + 6, pt + 4, now, (213, 201, 226, 51))
    put(g, pole_x - 2, pt + 1, "GAS", 213, True)
    put(g, pole_x - 3, pt + 2, "$0.86", 46 if math.sin(now * 3) < 0.9 else 22, True)
    put(g, pole_x - 3, pt + 3, "24 HRS", 51, True)
    palm(g, int(cols * 0.93), hy + 1, max(5, int(rows * 0.45)), -2, 96)  # big palms up front
    palm(g, int(cols * 0.56), hy, max(4, int(rows * 0.32)), 1, 96)
    car_x, car_y = int(cols * 0.03), rows - 1 - len(MUSCLE_CAR)  # the muscle car
    for i, line in enumerate(MUSCLE_CAR):
        body = line.rstrip()
        first = len(body) - len(body.lstrip())
        if i in (2, 3, 4) and body:
            fill(g, car_x + first, car_y + i, car_x + len(body), car_y + i + 1, 236)
    art(g, car_x, car_y, MUSCLE_CAR, 252)
    on = int(now * 2) % 2
    cell(g, car_x + 2, car_y + 3, "▮", 196 if on else 88, None, True)
    cell(g, car_x + 2, car_y + 4, "▮", 196 if on else 88, None, True)
    for k in range(4):  # exhaust puffs
        age = (now * 1.5 + k * 0.6) % 2.4
        cell(g, car_x - int(age * 2), car_y + 4 - int(age), "°o·"[min(2, int(age))], 250 if age < 1.2 else 245)
    draw_gas_duo(g, rows, cols, now)
    return g


def scene_frame(lm, rows, cols, now):
    name, place, fn = lm[:3]
    g = fn(rows, cols, now)
    put(g, 0, 0, (" ★ %s · %s " % (name.upper(), place))[:cols], 229, True, 53)
    back = " [E / Esc] back to the city "
    put(g, max(0, cols - len(back) - 1), rows - 1, back, 255, True, 53)
    return g


FAN_ART_SIZE = (150, 44)
FAN_ART_B64 = (
    "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"
    "EQ=="
)
_FAN_ART_CACHE = None


def _fan_art_data():
    global _FAN_ART_CACHE
    if _FAN_ART_CACHE is None:
        raw = zlib.decompress(base64.b64decode(FAN_ART_B64))
        n = FAN_ART_SIZE[0] * FAN_ART_SIZE[1]
        _FAN_ART_CACHE = (raw[:n].decode("ascii"), raw[n:])
    return _FAN_ART_CACHE


def scene_fan_art(rows, cols, now):
    g = canvas(rows, cols, bg=16)
    chars, colors = _fan_art_data()
    aw, ah = FAN_ART_SIZE
    avail_w, avail_h = cols, max(4, rows - 2)
    tw = min(avail_w, max(10, int(round(avail_h * aw / ah))))
    th = min(avail_h, max(4, int(round(tw * ah / aw))))
    x0 = (cols - tw) // 2
    y0 = 1 + (avail_h - th) // 2
    pulse = int(now * 3) % 4 == 0
    for ry in range(th):
        sy = min(ah - 1, int(ry * ah / th))
        row_off = sy * aw
        gy = y0 + ry
        for rx in range(tw):
            sx = min(aw - 1, int(rx * aw / tw))
            idx = row_off + sx
            ch = chars[idx]
            if ch != " ":
                fg = colors[idx]
                if pulse and fg == 231 and sy < 12 and 42 <= sx <= 68:
                    fg = 229  # gentle sunset sun shimmer
                cell(g, x0 + rx, gy, ch, fg, 16, True)
    return g


# --------------------------------------------------------------------------- game screen

HELP = [
    "  VIBE CITY  -  controls  ",
    "",
    "  arrows / WASD   cruise around",
    "  TAB             sprint (3x speed)",
    "  G               ghost mode: walk on water & roofs",
    "  M               full city map",
    "  T               skip ahead 2 hours (sunrise / sunset)",
    "  R               next radio station",
    "  N               next song on this station",    "  V               sound on / off",
    "  E               enter a ★ landmark when you're next to it",
    "  ?               toggle this help",
    "  Q               quit",
    "",
    "  fan tribute · GTA VI launch · original map",
]


class State:
    def __init__(self, spawn):
        self.px, self.py = spawn
        self.map_mode = self.ghost = self.sprint = False
        self.help = True
        self.scene = None
        self.radio = None
        self.district = None
        self.toast, self.toast_until = "", 0.0
        self.time_offset = 0  # game minutes added with the T key

def try_move(world, st, dx, dy):
    for _ in range(3 if st.sprint else 1):
        nx, ny = st.px + dx, st.py + dy
        if not (0 <= nx < W and 0 <= ny < H):
            break
        if not st.ghost and world.g[ny][nx] in SOLID:
            break
        st.px, st.py = nx, ny


def game_frame(world, st, cars, rows, cols, now):
    vh, vw = rows - 2, cols
    if st.map_mode:
        def w2s(x, y):
            return x * vw // W, y * vh // H

        def s2w(sx, sy):
            return min(W - 1, sx * W // vw), min(H - 1, sy * H // vh)
    else:
        cx = (st.px - vw // 2) if W > vw else -((vw - W) // 2)
        cy = (st.py - vh // 2) if H > vh else -((vh - H) // 2)
        if W > vw:
            cx = max(0, min(cx, W - vw))
        if H > vh:
            cy = max(0, min(cy, H - vh))

        def w2s(x, y):
            return x - cx, y - cy

        def s2w(sx, sy):
            return sx + cx, sy + cy

    ov = {}  # screen cell -> (ch, fg, bg or None, bold)

    def text_at(x, y, text, fg, bg=None, bold=True):
        sx, sy = w2s(x, y)
        for i, ch in enumerate(text):
            ov[(sx + i, sy)] = (ch, fg, bg, bold)

    m = clock_minutes(now, st.time_offset)
    day, lit = daylight(m), lit_fraction(m, daylight(m))
    for i, (x, y, text) in enumerate(world.signs):
        if day > 0.6:
            text_at(x, y, text, 245, 16)  # neon tubes switched off by day
            continue
        if math.sin(now * 6 + i * 2.3) > 0.93:
            continue  # neon flicker
        text_at(x, y, text, [201, 51, 226, 213][(i + int(now / 2)) % 4], 16)
    for name, x, y in LABELS:
        text_at(x, y, " " + name + " ", 255, 16)
    for lm in world.landmarks:
        if len(lm) > 5 and lm[5]:
            continue  # hidden treasure: no blinking star on the map
        sx, sy = w2s(lm[3], lm[4])
        ov[(sx, sy)] = ("★", 226 if int(now * 3) % 2 else 208, None, True)
    for c in cars:
        sx, sy = w2s(c.x, c.y)
        ov[(sx, sy)] = (CAR_GLYPH[c.d], c.fg, None, True)

    grid = []
    for sy in range(vh):
        row = []
        for sx in range(vw):
            wx, wy = s2w(sx, sy)
            if 0 <= wx < W and 0 <= wy < H:
                ch, fg, bg = world.look(wx, wy, now, day, lit)
            else:
                ch, fg, bg = " ", 0, 16
            o = ov.get((sx, sy))
            if o:
                row.append((o[0], o[1], bg if o[2] is None else o[2], o[3]))
            else:
                row.append((ch, fg, bg, False))
        grid.append(row)

    # the player: solid tile with a pulsing glow around it
    psx, psy = w2s(st.px, st.py)
    pulse = (math.sin(now * 6) + 1) / 2
    tile_bg = 231 if st.ghost else 201
    glow = (189 if pulse > 0.5 else 146) if st.ghost else (162 if pulse > 0.5 else 125)
    if not st.map_mode or int(now * 4) % 2 == 0:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                gx, gy = psx + dx, psy + dy
                if (dx or dy) and 0 <= gy < vh and 0 <= gx < vw:
                    ch, fg, _, bold = grid[gy][gx]
                    grid[gy][gx] = (ch, fg, glow, bold)
        if 0 <= psy < vh and 0 <= psx < vw:
            grid[psy][psx] = ("◆", 16, tile_bg, True)
    # district toast
    near = world.near(st.px, st.py, st.ghost)
    if now < st.toast_until and vh > 6:
        put(grid, max(0, (vw - len(st.toast)) // 2), 1, st.toast, 16, True, 213)
    elif near and vh > 6:
        msg = "  ★ press E to enter %s ★  " % near[0].upper()
        put(grid, max(0, (vw - len(msg)) // 2), 1, msg, 16, True, 226)
    # help box
    if st.help and vh > len(HELP) + 2:
        bw = max(len(s) for s in HELP) + 2
        bx, by = max(0, (vw - bw) // 2), max(0, (vh - len(HELP)) // 2)
        for i, line in enumerate(HELP):
            put(grid, bx, by + i, line.ljust(bw), 229 if i == 0 else 255, i == 0, 53)

    # HUD
    hud = [(" " * cols, 255, 16, False)]
    dname = world.district(st.px, st.py)
    vibes, _ = DISTRICTS[dname]
    clock = m
    radio = st.radio
    if radio and radio.available:
        station, song = radio.station["name"], radio.title
        if radio.status():
            song += " (%s)" % radio.status()
    else:
        station, song = RADIO[int(now / 20) % len(RADIO)]
    segs = [
        (" VIBE CITY ", 16, 201, True),
        (" " + dname + " ", 51, 16, True),
        (" VIBES " + "▮" * vibes + "▯" * (5 - vibes) + " ", 213, 16, False),
        (" %02d:%02d %s " % (clock // 60, clock % 60, phase_name(clock)), 229, 16, True),
        (" ♪ %s — %s " % (station, song), 123, 16, False),
    ]
    if st.ghost:
        segs.append((" GHOST ", 16, 231, True))
    if st.sprint:
        segs.append((" SPRINT ", 16, 226, True))
    top = [(" ", 255, 16, False)] * cols
    x = 0
    for text, fg, bg, bold in segs:
        for ch in text:
            if x < cols:
                top[x] = (ch, fg, bg, bold)
                x += 1
    foot_txt = (" ←↑→↓/WASD move  E enter ★  T +2h  R station  N song  V sound  TAB sprint  G ghost  M map  ? help  Q quit"
                "   ·  fan tribute to the GTA VI launch  ")
    foot = [(" ", 245, 16, False)] * cols
    for i, ch in enumerate(foot_txt[:cols - 1]):
        foot[i] = (ch, 245, 16, False)
    return [top] + grid + [foot]


def game(scr, pal, ascii_mode, radio=None):
    rnd = random.Random()
    world = World()
    cars = spawn_cars(world, 90, rnd)
    st = State(world.spawn)
    st.radio = radio
    t0 = last_car = time.time()
    moves = {
        curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1),
        curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0),
        ord("w"): (0, -1), ord("s"): (0, 1), ord("a"): (-1, 0), ord("d"): (1, 0),
        ord("W"): (0, -1), ord("S"): (0, 1), ord("A"): (-1, 0), ord("D"): (1, 0),
    }
    while True:
        while True:
            k = scr.getch()
            if k == -1:
                break
            if radio and k in (ord("r"), ord("R"), ord("n"), ord("N")):
                if k in (ord("r"), ord("R")):
                    radio.next_station()
                else:
                    radio.next_song()
                st.toast = "  ♪ %s — %s  " % (radio.station["name"], radio.title)
                st.toast_until = time.time() - t0 + 2.5
                continue
            if radio and k in (ord("v"), ord("V")):
                radio.toggle()
                st.toast = "  ♪ sound %s  " % ("on" if radio.on else "off")
                st.toast_until = time.time() - t0 + 1.5
                continue
            if st.scene:
                if k in (27, ord("e"), ord("E"), ord("q"), ord("Q"), 10, 13,
                         curses.KEY_ENTER, curses.KEY_BACKSPACE, 127):
                    st.scene = None
                    pal.reset()
                    scr.erase()
                elif k == curses.KEY_RESIZE:
                    scr.erase()
                continue
            if k in (ord("e"), ord("E"), 10, 13, curses.KEY_ENTER):
                lm = world.near(st.px, st.py, st.ghost)
                if lm:
                    st.scene, st.help = lm, False
                    pal.reset()  # each scene gets the full set of colour pairs
                    scr.erase()
            elif k in moves:
                try_move(world, st, *moves[k])
                st.help = False
            elif k in (ord("q"), ord("Q")):
                return
            elif k == 9:
                st.sprint = not st.sprint
            elif k in (ord("t"), ord("T")):
                st.time_offset += 120
            elif k in (ord("g"), ord("G")):
                st.ghost = not st.ghost
                if not st.ghost and world.g[st.py][st.px] in SOLID:
                    st.px, st.py = world.spawn  # don't leave the player stuck in the sea
            elif k in (ord("m"), ord("M")):
                st.map_mode = not st.map_mode
            elif k in (ord("?"), ord("h"), ord("H")):
                st.help = not st.help
            elif k == 27:
                st.help = st.map_mode = False
            elif k == curses.KEY_RESIZE:
                scr.erase()
        t = time.time()
        now = t - t0
        if t - last_car > 0.09:
            for c in cars:
                step_car(world, c, rnd)
            last_car = t
        d = world.district(st.px, st.py)
        if d != st.district:
            st.district = d
            st.toast = "  ◆ %s ◆  %s  " % (d.upper(), DISTRICTS[d][1])
            st.toast_until = now + 2.5
        rows, cols = scr.getmaxyx()
        if rows < 10 or cols < 40:
            scr.erase()
            try:
                scr.addstr(0, 0, "Vibe City needs at least 40x10 - make the window bigger")
            except curses.error:
                pass
        elif st.scene:
            flush(scr, pal, scene_frame(st.scene, rows, cols, now), 0, ascii_mode)
        else:
            frame = game_frame(world, st, cars, rows, cols, now)
            flush(scr, pal, frame, 0, ascii_mode)
            if pal.full:  # colours shifted with the daylight; recycle pairs and redraw
                pal.reset()
                flush(scr, pal, frame, 0, ascii_mode)
        scr.refresh()
        curses.napms(40)


def main(scr, ascii_mode):
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    scr.nodelay(True)
    scr.keypad(True)
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass
    pal = Palette()
    radio = None
    if "--mute" not in sys.argv:
        try:
            from radio import Radio
            radio = Radio()  # starts playing on the title screen
        except Exception:
            radio = None
    try:
        if splash(scr, pal, ascii_mode):
            pal.reset()
            scr.erase()
            game(scr, pal, ascii_mode, radio)
    finally:
        if radio:
            radio.stop()  # never leave afplay running after we quit


if __name__ == "__main__":
    os.environ.setdefault("ESCDELAY", "25")  # make Esc respond instantly
    locale.setlocale(locale.LC_ALL, "")
    try:
        curses.wrapper(main, "--ascii" in sys.argv)
    except KeyboardInterrupt:
        pass
    print("Thanks for cruising Vibe City. ◆")
