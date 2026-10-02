#!/usr/bin/env python3
"""Animated isometric 3D GitHub contribution calendar.

Fetches the user's real contribution calendar via the GitHub GraphQL API and
renders it as blue 3D blocks on a charcoal background, with a gentle wave
rippling across the blocks (SMIL animation, renders natively on GitHub).

Output: profile-3d-contrib/contrib-3d-animated.svg (relative to repo root).
"""

import json
import os
import sys
import urllib.request
from datetime import datetime

# ---------------------------------------------------------------- theme ---
BG = "#0D1117"
BORDER = "#21262D"
TEXT = "#C9D1D9"
MUTED = "#8B949E"
# contribution levels: none -> max (GitHub blue ramp)
RAMP = ["#161B22", "#0E3055", "#005CC5", "#2F81F7", "#58A6FF"]
# GitHub's own 5 greens, used to recover the quartile for each day
GH_GREEN = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]

# -------------------------------------------------------------- geometry ---
EX, EY = 9, 5            # diamond half-width / half-height (px)
H_BASE, H_STEP = 2, 9    # block height = H_BASE + level * H_STEP

# ------------------------------------------------------------------ wave ---
WAVE_DUR = 3.6           # seconds per ripple cycle
WAVE_STEP = 0.045        # phase delay between consecutive blocks
WAVE_AMP = 7             # ripple height (px)


def shade(hexcolor, factor):
    h = hexcolor.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#%02x%02x%02x" % (int(r * factor), int(g * factor), int(b * factor))


def fetch_calendar(login, token):
    query = (
        "query($login:String!){user(login:$login){"
        "contributionsCollection{contributionCalendar{"
        "totalContributions "
        "weeks{contributionDays{date contributionCount color}}}}}}"
    )
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": login}}).encode(),
        headers={
            "Authorization": "Bearer %s" % token,
            "Content-Type": "application/json",
            "User-Agent": "contrib-3d-anim",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def level_of(github_color):
    try:
        return GH_GREEN.index(github_color.lower())
    except ValueError:
        return 0


def block_polygons(w, d, h):
    """Return (top, left, right) polygons for the 3D block at week w, day d."""
    cx = (w - d) * EX
    cy = (w + d) * EY          # top-face center of a flat tile
    tcy = cy - h               # top-face center raised by block height
    top = [(cx, tcy - EY), (cx + EX, tcy), (cx, tcy + EY), (cx - EX, tcy)]
    left = [(cx - EX, tcy), (cx, tcy + EY), (cx, cy + EY), (cx - EX, cy)]
    right = [(cx + EX, tcy), (cx, tcy + EY), (cx, cy + EY), (cx + EX, cy)]
    return top, left, right


def pts(poly):
    return " ".join("%d,%d" % (x, y) for x, y in poly)


def build_svg(cal):
    weeks = cal["weeks"]
    total = cal["totalContributions"]

    cells = []  # (w, d, level)
    for w, week in enumerate(weeks):
        for d, day in enumerate(week["contributionDays"]):
            cells.append((w, d, level_of(day["color"]), day["date"]))

    # painter's algorithm: draw back rows first
    cells.sort(key=lambda c: (c[0] + c[1], c[0]))

    max_h = H_BASE + 4 * H_STEP
    min_x = -6 * EX
    max_x = (len(weeks) - 1) * EX
    min_y = -max_h - EY - 34          # room for month labels
    max_y = (len(weeks) - 1 + 6) * EY + 26   # room for shadow

    pad = 26
    vb = (min_x - pad, min_y - pad,
          (max_x - min_x) + 2 * pad, (max_y - min_y) + 2 * pad)

    out = []
    a = out.append
    a('<?xml version="1.0" encoding="UTF-8"?>')
    a('<svg xmlns="http://www.w3.org/2000/svg" viewBox="%d %d %d %d" '
      'role="img" aria-label="3D contribution calendar">' % vb)
    a("<title>Animated 3D contribution calendar</title>")
    a("<defs>")
    a('<filter id="soft" x="-40%" y="-40%" width="180%" height="180%">'
      '<feGaussianBlur stdDeviation="9"/></filter>')
    a("</defs>")

    # backdrop
    a('<rect x="%d" y="%d" width="%d" height="%d" rx="14" fill="%s" '
      'stroke="%s" stroke-width="1"/>' % (vb[0], vb[1], vb[2], vb[3], BG, BORDER))

    # soft shadow under the whole calendar
    sh_cx = (min_x + max_x) / 2
    sh_y = (len(weeks) - 1 + 6) * EY + 12
    a('<ellipse cx="%.1f" cy="%.1f" rx="%.1f" ry="15" fill="#000000" '
      'opacity="0.45" filter="url(#soft)"/>' % (sh_cx, sh_y, (max_x - min_x) / 2))

    # caption: total contributions
    a('<text x="%d" y="%d" font-size="12" fill="%s" font-family="Ubuntu,'
      'Helvetica,Arial,sans-serif">%d contributions in the last year</text>'
      % (min_x, min_y + 16, MUTED, total))

    # month labels where the month changes
    prev_month = None
    for w, week in enumerate(weeks):
        days = week["contributionDays"]
        if not days:
            continue
        month = datetime.strptime(days[0]["date"], "%Y-%m-%d").strftime("%b")
        if month != prev_month:
            prev_month = month
            a('<text x="%d" y="%d" font-size="10" fill="%s" text-anchor="middle" '
              'font-family="Ubuntu,Helvetica,Arial,sans-serif">%s</text>'
              % (w * EX, w * EY - max_h - 12, MUTED, month))

    # blocks, each riding the wave
    for i, (w, d, level, _date) in enumerate(cells):
        h = H_BASE + level * H_STEP
        color = RAMP[level]
        top, left, right = block_polygons(w, d, h)
        begin = (w * 7 + d) * WAVE_STEP
        a('<g>')
        a('<animateTransform attributeName="transform" type="translate" '
          'values="0 0; 0 -%d; 0 0" keyTimes="0; 0.5; 1" calcMode="spline" '
          'keySplines="0.4 0 0.6 1; 0.4 0 0.6 1" dur="%.1fs" begin="%.2fs" '
          'repeatCount="indefinite"/>' % (WAVE_AMP, WAVE_DUR, begin))
        a('<polygon points="%s" fill="%s"/>' % (pts(left), shade(color, 0.68)))
        a('<polygon points="%s" fill="%s"/>' % (pts(right), shade(color, 0.52)))
        a('<polygon points="%s" fill="%s"/>' % (pts(top), color))
        a('</g>')

    a("</svg>")
    return "\n".join(out)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GITHUB_USER")
    if not token or not login:
        sys.exit("GITHUB_TOKEN and GITHUB_USER must be set")
    cal = fetch_calendar(login, token)
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    out_dir = os.path.join(root, "profile-3d-contrib")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "contrib-3d-animated.svg")
    with open(out_path, "w") as f:
        f.write(build_svg(cal))
    print("wrote %s (%d contributions)" % (out_path, cal["totalContributions"]))


if __name__ == "__main__":
    main()
