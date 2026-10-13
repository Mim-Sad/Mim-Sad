#!/usr/bin/env python3
"""Render the SVG widgets used by the profile README.

Standard library only. Every widget is drawn here, in a light and a dark
variant, with subsetted Inter / JetBrains Mono embedded so typography is
identical on every device. Nothing depends on third-party image services.

    python scripts/profile_cards.py            # live data (needs GITHUB_TOKEN)
    python scripts/profile_cards.py --mock     # deterministic fake data
    python scripts/profile_cards.py --static   # hero + toolkit only
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import math
import os
import random
import sys
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "scripts" / "fonts"
SRC = ROOT / "assets"
OUT = Path(os.environ.get("PROFILE_OUT", SRC))
USER = os.environ.get("PROFILE_USER", "Mim-Sad")

THEMES = {
    "dark": {
        "surface": "#0f141b", "edge": "#232a34", "chip": "#151b23",
        "text": "#e6edf3", "muted": "#8b949e", "faint": "#5b6470", "grid": "#1a212b",
        "accent": "#5eead4", "accent2": "#a5b4fc",
        "levels": ["#161b22", "#0f4a43", "#13806f", "#2fbfa3", "#7ff0d6"],
    },
    "light": {
        "surface": "#ffffff", "edge": "#d8dee4", "chip": "#f6f8fa",
        "text": "#1f2328", "muted": "#59636e", "faint": "#8c959f", "grid": "#eef1f4",
        "accent": "#0d9488", "accent2": "#6366f1",
        "levels": ["#ebedf0", "#b8ecdf", "#5fd3bb", "#14a38c", "#0b6e60"],
    },
}

W, H, M = 400, 200, 5          # canvas, outer margin (gutter between cards)
PAD = 24                        # content padding inside a card
X0, X1 = M + PAD, W - M - PAD   # content box
WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


# --------------------------------------------------------------------------
# typography
# --------------------------------------------------------------------------
METRICS = json.loads((FONTS / "metrics.json").read_text())
SANS = "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "'JetBrains Mono','SF Mono',Menlo,Consolas,monospace"
_FAMILY = {"inter-400": ("Inter", 400), "inter-500": ("Inter", 500),
           "inter-600": ("Inter", 600), "mono-400": ("JetBrains Mono", 400)}


def font_css(*names: str) -> str:
    css = []
    for n in names:
        fam, weight = _FAMILY[n]
        b64 = base64.b64encode((FONTS / f"{n}.woff2").read_bytes()).decode()
        css.append(f"@font-face{{font-family:'{fam}';font-weight:{weight};"
                   f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "".join(css)


def text_width(s: str, size: float, font: str = "inter-500", tracking: float = 0) -> float:
    m = METRICS[font]
    return sum(m.get(c, 0.6) for c in s) * size + tracking * max(len(s) - 1, 0)


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
QUERY = """
query($login:String!, $cursor:String) {
  user(login:$login) {
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(ownerAffiliations:OWNER, isFork:false, first:100, after:$cursor,
                 orderBy:{field:PUSHED_AT, direction:DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first:10, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def gql(token: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-cards"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]["user"]


def fetch(token: str, login: str) -> dict:
    """Fetch everything the cards need (follows repo pagination)."""
    user, cursor, nodes = None, None, []
    while True:
        page = gql(token, {"login": login, "cursor": cursor})
        user = user or page
        nodes += page["repositories"]["nodes"]
        info = page["repositories"]["pageInfo"]
        if not info["hasNextPage"]:
            break
        cursor = info["endCursor"]

    langs: dict[str, dict] = {}
    for repo in nodes:
        for e in repo["languages"]["edges"]:
            slot = langs.setdefault(e["node"]["name"], {"size": 0, "color": e["node"]["color"] or "#8b949e"})
            slot["size"] += e["size"]

    cc = user["contributionsCollection"]
    days = [
        {"date": d["date"], "count": d["contributionCount"]}
        for w in cc["contributionCalendar"]["weeks"]
        for d in w["contributionDays"]
    ]
    return {
        "login": login,
        "followers": user["followers"]["totalCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in nodes),
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "total": cc["contributionCalendar"]["totalContributions"],
        "days": days,
        "langs": langs,
    }


def mock_data(seed: int = 7) -> dict:
    rnd = random.Random(seed)
    end = dt.date(2026, 10, 13)
    days = []
    for i in range(365, -1, -1):
        d = end - dt.timedelta(days=i)
        season = 1 + 0.6 * math.sin(i / 58)
        idle = rnd.random() < (0.05 if i < 12 else 0.24)
        count = 0 if idle else int(rnd.randint(1, 9) * season + (3 if d.weekday() in (1, 2, 3) else 0))
        days.append({"date": d.isoformat(), "count": count})
    return {
        "login": USER, "followers": 128, "prs": 64, "issues": 21, "repos": 47,
        "stars": 312, "commits": 1873, "total": sum(d["count"] for d in days),
        "days": days,
        "langs": {
            "Python": {"size": 540_000, "color": "#3572A5"},
            "JavaScript": {"size": 310_000, "color": "#f1e05a"},
            "C#": {"size": 220_000, "color": "#178600"},
            "TypeScript": {"size": 140_000, "color": "#3178c6"},
            "C++": {"size": 90_000, "color": "#f34b7d"},
            "HTML": {"size": 60_000, "color": "#e34c26"},
            "CSS": {"size": 30_000, "color": "#563d7c"},
        },
    }


# --------------------------------------------------------------------------
# computations
# --------------------------------------------------------------------------
def streaks(days: list[dict], today: dt.date | None = None) -> tuple[int, int]:
    """(current, longest). Today with zero commits doesn't break a live streak."""
    today = today or dt.date.fromisoformat(days[-1]["date"])
    longest = run = 0
    for d in days:
        run = run + 1 if d["count"] > 0 else 0
        longest = max(longest, run)
    cur = 0
    for d in reversed(days):
        if d["count"] > 0:
            cur += 1
        elif dt.date.fromisoformat(d["date"]) == today:
            continue
        else:
            break
    return cur, longest


def weekday_totals(days: list[dict]) -> list[int]:
    out = [0] * 7
    for d in days:
        out[(dt.date.fromisoformat(d["date"]).weekday() + 1) % 7] += d["count"]
    return out


def level(count: int, peak: int) -> int:
    if count <= 0:
        return 0
    return min(1 + int(count / max(peak, 1) * 3.999), 4)


def short_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d:%b} {d.day}"


# --------------------------------------------------------------------------
# svg primitives
# --------------------------------------------------------------------------
def fmt(n: int) -> str:
    if n >= 10_000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n:,}"


def doc(w: int, h: int, body: str, title: str, defs: str = "", fonts=("inter-400", "inter-600")) -> str:
    style = font_css(*fonts) + (
        "text{font-family:" + SANS + ";font-feature-settings:'tnum','cv11'}"
        ".mono{font-family:" + MONO + "}"
        # Elements are visible by default; `both` fill only hides them during their delay,
        # so renderers that skip animation still show the finished card.
        ".a{animation:rise .7s cubic-bezier(.2,.7,.2,1) both;animation-delay:var(--d,0s)}"
        "@keyframes rise{from{opacity:0;transform:translateY(10px)}}"
        ".fade{animation:fade .8s ease both;animation-delay:var(--d,0s)}"
        "@keyframes fade{from{opacity:0}}"
        ".grow{transform-box:fill-box;transform-origin:50% 100%;"
        "animation:grow .9s cubic-bezier(.2,.9,.25,1.05) both;animation-delay:var(--d,0s)}"
        "@keyframes grow{from{transform:scaleY(0)}}"
        ".sweep{transform-box:fill-box;transform-origin:0 50%;"
        "animation:sweep .9s cubic-bezier(.2,.8,.2,1) both;animation-delay:var(--d,0s)}"
        "@keyframes sweep{from{transform:scaleX(0)}}"
        ".pop{transform-box:fill-box;transform-origin:50% 50%;"
        "animation:pop .55s cubic-bezier(.3,1.5,.5,1) both;animation-delay:var(--d,0s)}"
        "@keyframes pop{from{opacity:0;transform:scale(.55)}}"
        ".draw{stroke-dasharray:1;animation:draw 1.6s cubic-bezier(.4,.1,.2,1) .25s both}"
        "@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
        ".beat{transform-box:fill-box;transform-origin:50% 50%;animation:beat 2.6s ease-out 2s infinite}"
        "@keyframes beat{0%{transform:scale(1);opacity:.5}70%,100%{transform:scale(2.4);opacity:0}}"
        "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{escape(title)}">\n<title>{escape(title)}</title>\n'
        f"<defs><style>{style}</style>{defs}</defs>\n{body}\n</svg>\n"
    )


def dly(i: float, base: float = .1, step: float = .06) -> str:
    return f' style="--d:{base + i * step:.2f}s"'


def label(x, y, s, t, size=11.5, anchor="start", color=None, weight=400, spacing=0):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}"{ls} '
            f'fill="{color or t["muted"]}" text-anchor="{anchor}">{escape(s)}</text>')


def value(x, y, s, t, size=24, anchor="start", color=None):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="600" letter-spacing="-.4" '
            f'fill="{color or t["text"]}" text-anchor="{anchor}">{escape(s)}</text>')


def frame(t: dict, w: int, h: int, rx: int = 12) -> str:
    return (f'<rect x="{M + .5}" y="{M + .5}" width="{w - 2 * M - 1}" height="{h - 2 * M - 1}" '
            f'rx="{rx}" fill="{t["surface"]}" stroke="{t["edge"]}"/>')


def card(t: dict, title: str, meta: str, inner: str, h: int = H, defs: str = "",
         fonts=("inter-400", "inter-600")) -> str:
    body = (
        frame(t, W, h)
        + f'<g class="a"{dly(0, .05)}>' + label(X0, M + 33, title, t, 13, color=t["text"], weight=600)
        + (label(X1, M + 33, meta, t, 11.5, "end") if meta else "") + "</g>"
        + inner
    )
    return doc(W, h, body, title, defs, fonts)


# --------------------------------------------------------------------------
# cards
# --------------------------------------------------------------------------
def overview_card(d: dict, t: dict) -> str:
    items = [
        ("Commits · 1y", d["commits"]), ("Pull requests", d["prs"]), ("Issues", d["issues"]),
        ("Stars", d["stars"]), ("Followers", d["followers"]), ("Repositories", d["repos"]),
    ]
    col = (X1 - X0) / 3
    out = [f'<line x1="{X0}" x2="{X1}" y1="124.5" y2="124.5" stroke="{t["grid"]}"/>']
    for i, (name, n) in enumerate(items):
        x, y = X0 + (i % 3) * col, 88 + (i // 3) * 64
        out.append(f'<g class="a"{dly(i, .15, .08)}>' + value(x, y, fmt(n), t) + label(x, y + 19, name, t) + "</g>")
    return card(t, "Overview", f"@{d['login']}", "".join(out))


def streak_card(d: dict, t: dict) -> str:
    cur, longest = streaks(d["days"])
    recent = d["days"][-14:]
    peak = max(x["count"] for x in d["days"]) or 1
    out = [
        f'<g class="a"{dly(0, .15)}>',
        value(X0, 98, str(cur), t, 40).replace(
            "</text>", f'<tspan dx="6" font-size="13" font-weight="400" letter-spacing="0" '
                       f'fill="{t["muted"]}">{"day" if cur == 1 else "days"}</tspan></text>'),
        label(X0, 119, "Current streak", t),
        "</g>",
    ]
    rx = M + 222
    out += [f'<line x1="{rx - 22.5}" x2="{rx - 22.5}" y1="62" y2="150" stroke="{t["grid"]}"/>',
            f'<g class="a"{dly(0, .3)}>', value(rx, 82, f"{longest} days", t, 17), label(rx, 100, "Longest streak", t), "</g>",
            f'<g class="a"{dly(0, .42)}>', value(rx, 132, fmt(d["total"]), t, 17), label(rx, 150, "Contributions · 1y", t), "</g>"]
    gap = 4
    size = (rx - 46 - X0 - gap * 13) / 14
    for i, x in enumerate(recent):
        out.append(f'<rect class="pop"{dly(i, .45, .04)} x="{X0 + i * (size + gap):.1f}" y="136" '
                   f'width="{size:.1f}" height="{size:.1f}" rx="2" fill="{t["levels"][level(x["count"], peak)]}"/>')
    out.append(f'<g class="fade"{dly(0, 1.0)}>' + label(X0, 168, "Last 14 days", t, 10.5, color=t["faint"]) + "</g>")
    return card(t, "Streak", "", "".join(out))


def languages_card(d: dict, t: dict) -> str:
    langs = sorted(d["langs"].items(), key=lambda kv: -kv[1]["size"])
    total = sum(v["size"] for _, v in langs) or 1
    rows = [(n, v["size"], v["color"]) for n, v in langs[:5]]
    rest = total - sum(r[1] for r in rows)
    if rows and rest > 0:
        rows.append(("Other", rest, t["faint"]))

    width, gap, x = X1 - X0, 2, float(X0)
    defs = f'<clipPath id="bar"><rect x="{X0}" y="60" width="{width}" height="8" rx="4"/></clipPath>'
    bar = [f'<g clip-path="url(#bar)"><rect x="{X0}" y="60" width="{width}" height="8" fill="{t["grid"]}"/>']
    for i, (_, size, color) in enumerate(rows):
        w = size / total * width
        bar.append(f'<rect class="sweep"{dly(i, .15, .08)} x="{x:.1f}" y="60" width="{max(w - gap, .5):.1f}" '
                   f'height="8" fill="{color}"/>')
        x += w
    bar.append("</g>")

    legend, colw = [], (width - 28) / 2
    for i, (name, size, color) in enumerate(rows):
        cx, cy = X0 + (i % 2) * (colw + 28), 104 + (i // 2) * 28
        legend.append(
            f'<g class="a"{dly(i, .3, .07)}><circle cx="{cx + 4}" cy="{cy - 4}" r="4" fill="{color}"/>'
            + label(cx + 16, cy, name, t, 12.5, color=t["text"])
            + label(cx + colw, cy, f"{size / total * 100:.1f}%", t, 12, "end") + "</g>"
        )
    if not rows:
        legend.append(label(X0, 110, "No language data yet", t, 12))
    return card(t, "Languages", "by code size", "".join(bar + legend), defs=defs)


def bar_chart(t: dict, values: list[int], names: list[str], bw: float) -> tuple[str, int]:
    peak = max(values) or 1
    best = values.index(max(values))
    step = (X1 - X0 - bw) / (len(values) - 1)
    base, top = 148, 66
    out = [f'<line x1="{X0}" x2="{X1}" y1="{base + .5}" y2="{base + .5}" stroke="{t["grid"]}"/>']
    for i, v in enumerate(values):
        hgt = max(v / peak * (base - top), 2)
        x = X0 + i * step
        hot = i == best and v > 0
        out.append(
            f'<rect class="grow"{dly(i, .1, .05)} x="{x:.1f}" y="{base - hgt:.1f}" width="{bw}" height="{hgt:.1f}" rx="{min(bw / 2, 4)}" '
            f'fill="{t["accent"]}" fill-opacity="{1 if hot else .26}"/>'
            + f'<g class="fade"{dly(i, .3, .05)}>' + label(x + bw / 2, base + 22, names[i], t, 11, "middle",
                    color=t["text"] if hot else t["faint"], weight=600 if hot else 400) + "</g>"
        )
    return "".join(out), best


def weekly_card(d: dict, t: dict) -> str:
    chart, best = bar_chart(t, weekday_totals(d["days"]), WEEKDAYS, 26)
    return card(t, "Weekly rhythm", f"Most active · {WEEKDAYS[best]}", chart)


def monthly_card(d: dict, t: dict) -> str:
    months: dict[str, int] = {}
    for x in d["days"]:
        months[x["date"][:7]] = months.get(x["date"][:7], 0) + x["count"]
    keys = sorted(months)[-12:]
    names = [dt.date.fromisoformat(k + "-01").strftime("%b")[0] for k in keys]
    chart, best = bar_chart(t, [months[k] for k in keys], names, 14)
    best_name = dt.date.fromisoformat(keys[best] + "-01").strftime("%b")
    return card(t, "Past 12 months", f"Best · {best_name}", chart)


def activity_card(d: dict, t: dict, span: int = 30) -> str:
    days = d["days"][-span:]
    src = d["days"][-span - 2:]
    smooth = [sum(x["count"] for x in src[max(i - 2, 0):i + 1]) / len(src[max(i - 2, 0):i + 1])
              for i in range(len(src))][-span:]
    top, base = 66, 148
    peak = max(max(smooth), 1)
    step = (X1 - X0) / (len(days) - 1)
    pts = [(X0 + i * step, base - v / peak * (base - top)) for i, v in enumerate(smooth)]

    def seg(i):  # catmull-rom → bezier, control points clamped to the plot
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, len(pts) - 1)]
        k = lambda v: min(max(v, top), base)  # noqa: E731
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, k(p1[1] + (p2[1] - p0[1]) / 6))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, k(p2[1] - (p3[1] - p1[1]) / 6))
        return f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"

    line = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}" + "".join(seg(i) for i in range(len(pts) - 1))
    area = f"{line}L{pts[-1][0]:.1f},{base}L{pts[0][0]:.1f},{base}Z"
    defs = (f'<linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{t["accent"]}" stop-opacity=".22"/>'
            f'<stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/></linearGradient>')

    grid = "".join(f'<line x1="{X0}" x2="{X1}" y1="{y + .5:.1f}" y2="{y + .5:.1f}" stroke="{t["grid"]}"/>'
                   for y in (top, (top + base) / 2, base))
    ticks = "".join(label(pts[i][0], base + 22, short_date(days[i]["date"]), t, 11, a, color=t["faint"])
                    for i, a in ((0, "start"), (span // 2, "middle"), (span - 1, "end")))
    ex, ey = pts[-1]
    inner = (
        grid + f'<path class="fade"{dly(0, .9)} d="{area}" fill="url(#fill)"/>'
        f'<path class="draw" pathLength="1" d="{line}" fill="none" stroke="{t["accent"]}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle class="beat" cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="{t["accent"]}"/>'
        f'<circle class="pop"{dly(0, 1.7)} cx="{ex:.1f}" cy="{ey:.1f}" r="3.2" fill="{t["accent"]}"/>'
        + f'<g class="fade"{dly(0, .4)}>' + ticks + "</g>"
    )
    total = sum(x["count"] for x in days)
    return card(t, "Last 30 days", f"{fmt(total)} contributions", inner, defs=defs)


# --------------------------------------------------------------------------
# toolkit
# --------------------------------------------------------------------------
TOOLKIT = {
    "languages": ("Languages", [
        ("Core", ["Python", "TypeScript", "JavaScript", "PHP", "Dart", "SQL"]),
        ("Systems & enterprise", ["C#", "C++", "Java"]),
    ]),
    "apps": ("Apps & Engines", [
        ("Web & mobile", ["Flutter", "React", "Node.js", "WordPress", "HTML5", "CSS3"]),
        ("Game engines", ["Unity", "Unreal"]),
    ]),
    "ai": ("AI & Data", [
        ("Machine intelligence", ["LLMs", "Agents", "RAG", "ML", "Deep Learning", "RL"]),
        ("Data", ["SQLite", "MongoDB", "Colab"]),
    ]),
    "ops": ("Cloud & Design", [
        ("Infrastructure", ["Cloud Computing", "DevOps", "Docker", "Git", "Linux"]),
        ("Design & motion", ["Photoshop", "Illustrator", "After Effects"]),
    ]),
}


def _lum(hex_: str) -> float:
    rgb = [int(hex_.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
    return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + .05) / (lb + .05)


def toolkit_card(key: str, t: dict, height: int | None = None) -> tuple[str, int]:
    """Groups of icon pills, flowed into rows. Returns (svg, natural height)."""
    icons = json.loads((ROOT / "scripts" / "icons.json").read_text())
    title, groups = TOOLKIT[key]
    out, y, ph, gap, n = [], M + 64, 28, 7, 0
    for gname, items in groups:
        out.append(f'<g class="fade"{dly(n, .1, .03)}>'
                   + label(X0, y, gname.upper(), t, 10, color=t["faint"], weight=600, spacing=.8) + "</g>")
        y += 11
        x = X0
        for name in items:
            icon = icons.get(name)
            w = 10 + (16 + 7 if icon or name == "C#" else 0) + text_width(name, 12.5, "inter-500") + 11
            if x + w > X1:
                x, y = X0, y + ph + gap
            out.append(f'<g class="pop"{dly(n, .15, .045)}>'
                       f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{ph}" rx="8" '
                       f'fill="{t["chip"]}" stroke="{t["edge"]}"/>')
            n += 1
            tx = x + 10
            if name == "C#":  # not in simple-icons any more: hexagon mark
                out.append(f'<g transform="translate({tx + 8:.1f} {y + 14:.1f})">'
                           '<path d="M0-8 6.93-4V4L0 8-6.93 4V-4Z" fill="#7B3FB0"/>'
                           '<text y="2.6" font-size="7" font-weight="600" fill="#fff" '
                           'text-anchor="middle">C#</text></g>')
                tx += 23
            elif icon and "stroke" in icon:  # line icon (Lucide, ISC), tinted with the accent
                out.append(f'<g transform="translate({tx:.1f} {y + 6:.1f}) scale(.6667)" fill="none" '
                           f'stroke="{t["accent"]}" stroke-width="2.2" stroke-linecap="round" '
                           f'stroke-linejoin="round">{icon["stroke"]}</g>')
                tx += 23
            elif icon:
                color = "#" + icon["color"]
                if contrast(color, t["chip"]) < 2.2:
                    color = t["text"]
                out.append(f'<path transform="translate({tx:.1f} {y + 6:.1f}) scale(.6667)" '
                           f'd="{icon["d"]}" fill="{color}"/>')
                tx += 23
            out.append(f'<text x="{tx:.1f}" y="{y + 18.5:.1f}" font-size="12.5" font-weight="500" '
                       f'fill="{t["text"]}">{escape(name)}</text></g>')
            x += w + gap
        y += ph + 28
    natural = int(y - 28 + PAD + M)
    h = height or natural
    body = (frame(t, W, h) + f'<g class="a"{dly(0, .05)}>'
            + label(X0, M + 33, title, t, 13, color=t["text"], weight=600) + "</g>" + "".join(out))
    return doc(W, h, body, title, fonts=("inter-400", "inter-500", "inter-600")), natural


# --------------------------------------------------------------------------
# hero
# --------------------------------------------------------------------------
def hero(t: dict, theme: str) -> str:
    w, h = 2 * W + 4, 300
    avatar = base64.b64encode((SRC / "avatar.webp").read_bytes()).decode()
    ah = 272
    aw = ah * 359 / 560
    ax = w - M - 70 - aw
    gx = ax + aw / 2
    dark = theme == "dark"
    defs = (
        f'<clipPath id="c"><rect x="{M}" y="{M}" width="{w - 2 * M}" height="{h - 2 * M}" rx="16"/></clipPath>'
        f'<radialGradient id="glow" cx="{gx:.1f}" cy="{h * .64:.1f}" r="240" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{t["accent"]}" stop-opacity="{.16 if dark else .13}"/>'
        f'<stop offset=".55" stop-color="{t["accent2"]}" stop-opacity="{.07 if dark else .05}"/>'
        f'<stop offset="1" stop-color="{t["accent2"]}" stop-opacity="0"/></radialGradient>'
        f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
        f'<circle cx="1" cy="1" r="1" fill="{t["edge"]}"/></pattern>'
        f'<radialGradient id="fade" cx="{gx:.1f}" cy="{h / 2}" r="340" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="m"><rect width="{w}" height="{h}" fill="url(#fade)"/></mask>'
        f'<linearGradient id="name" x1="0" x2="1"><stop offset="0" stop-color="{t["accent"]}"/>'
        f'<stop offset="1" stop-color="{t["accent2"]}"/></linearGradient>'
        "<style>"
        ".cur{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
        ".orbit{transform-box:fill-box;transform-origin:50% 50%;animation:spin 90s linear infinite}"
        "@keyframes spin{to{transform:rotate(360deg)}}"
        ".glow{animation:breathe 7s ease-in-out infinite}"
        "@keyframes breathe{50%{opacity:.55}}"
        ".av{animation:avatar 1s cubic-bezier(.2,.8,.2,1) .15s both}"
        "@keyframes avatar{from{opacity:0;transform:translateY(28px) scale(.97)}}"
        ".slide{animation:slide .8s cubic-bezier(.2,.8,.2,1) both;animation-delay:var(--d,0s)}"
        "@keyframes slide{from{opacity:0;transform:translateX(-18px)}}"
        ".ping{transform-box:fill-box;transform-origin:center;animation:ping 2.4s ease-out infinite}"
        "@keyframes ping{0%{transform:scale(1);opacity:.55}80%,100%{transform:scale(2.6);opacity:0}}"
        "</style>"
    )
    x = M + 44
    status = "currently building with AI"
    sw = text_width(status, 12, "mono-400") + 46
    cy = h - 116
    body = f"""{frame(t, w, h, 16)}
<g clip-path="url(#c)">
  <rect width="{w}" height="{h}" fill="url(#dots)" mask="url(#m)"/>
  <rect class="glow" width="{w}" height="{h}" fill="url(#glow)"/>
  <circle cx="{gx:.1f}" cy="{cy}" r="116" fill="none" stroke="{t["edge"]}"/>
  <circle class="orbit" cx="{gx:.1f}" cy="{cy}" r="160" fill="none" stroke="{t["edge"]}" stroke-dasharray="2 7" stroke-linecap="round"/>
  <circle class="orbit" style="animation-direction:reverse;animation-duration:140s" cx="{gx:.1f}" cy="{cy}" r="200" fill="none" stroke="{t["edge"]}" stroke-opacity=".55" stroke-dasharray="1 11" stroke-linecap="round"/>
  <image class="av" href="data:image/webp;base64,{avatar}" x="{ax:.1f}" y="{h - M - ah + 4}" width="{aw:.1f}" height="{ah}"/>
</g>
<rect x="{M + .5}" y="{M + .5}" width="{w - 2 * M - 1}" height="{h - 2 * M - 1}" rx="16" fill="none" stroke="{t["edge"]}"/>
<g class="slide"{dly(0, .1)}><text x="{x}" y="76" class="mono" font-size="13" fill="{t["faint"]}">~/mim-sad <tspan fill="{t["accent"]}">&gt;</tspan> <tspan fill="{t["muted"]}">whoami</tspan><tspan class="cur" fill="{t["accent"]}"> ▌</tspan></text></g>
<g class="slide"{dly(0, .22)}><text x="{x - 2}" y="130" font-size="42" font-weight="600" letter-spacing="-1.2" fill="{t["text"]}">Mohammad Sadegh</text></g>
<g class="slide"{dly(0, .34)}><text x="{x - 2}" y="178" font-size="42" font-weight="600" letter-spacing="-1.2" fill="url(#name)">Taghizadeh</text></g>
<g class="slide"{dly(0, .46)}><text x="{x}" y="214" font-size="17" fill="{t["muted"]}">Full-stack developer <tspan fill="{t["faint"]}">&amp;</tspan> graphic designer</text></g>
<g class="pop"{dly(0, .62)}>
  <rect x="{x + .5}" y="236.5" width="{sw:.1f}" height="28" rx="14" fill="{t["chip"]}" stroke="{t["edge"]}"/>
  <circle class="ping" cx="{x + 17}" cy="250.5" r="3.5" fill="{t["accent"]}"/>
  <circle cx="{x + 17}" cy="250.5" r="3.5" fill="{t["accent"]}"/>
  <text x="{x + 30}" y="255" class="mono" font-size="12" fill="{t["muted"]}">{status}</text>
</g>"""
    return doc(w, h, body, "Mohammad Sadegh Taghizadeh, full-stack developer and graphic designer",
               defs, fonts=("inter-400", "inter-600", "mono-400"))


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------
def write(name: str, content: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"wrote {name:<26} {len(content) / 1024:5.1f} KB")


def build_static() -> None:
    for theme, t in THEMES.items():
        write(f"hero-{theme}.svg", hero(t, theme))
        # all toolkit cards share one height so the grid lines up
        h = max(toolkit_card(k, t)[1] for k in TOOLKIT)
        for k in TOOLKIT:
            write(f"toolkit-{k}-{theme}.svg", toolkit_card(k, t, h)[0])


CARDS = {
    "overview": overview_card, "streak": streak_card, "languages": languages_card,
    "weekly": weekly_card, "activity": activity_card, "monthly": monthly_card,
}


def build_dynamic(d: dict) -> None:
    for theme, t in THEMES.items():
        for name, fn in CARDS.items():
            write(f"{name}-{theme}.svg", fn(d, t))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--static", action="store_true", help="only hero + toolkit")
    args = ap.parse_args(argv)

    build_static()
    if args.static:
        return 0
    if args.mock:
        data = mock_data()
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            print("GITHUB_TOKEN is required (or use --mock)", file=sys.stderr)
            return 1
        data = fetch(token, USER)
    build_dynamic(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
