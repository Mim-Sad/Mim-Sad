#!/usr/bin/env python3
"""Generate the SVG widgets used by the profile README.

Standard library only. Everything is rendered locally into ./assets, so the
profile never depends on third-party image services at view time.

    python scripts/profile_cards.py            # live data (needs GITHUB_TOKEN)
    python scripts/profile_cards.py --mock     # deterministic fake data
    python scripts/profile_cards.py --static   # hero + tech stack only
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import random
import sys
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = Path(os.environ.get("PROFILE_OUT", ROOT / "assets"))
STATIC_SRC = ROOT / "assets"
USER = os.environ.get("PROFILE_USER", "Mim-Sad")

# Night Owl inspired palette
BG, CARD, EDGE = "#011627", "#0b2942", "#1d3b53"
TEXT, MUTED = "#d6deeb", "#7e97b8"
TEAL, PURPLE, YELLOW, BLUE, PINK = "#7fdbca", "#c792ea", "#ecc48d", "#82aaff", "#f78c6c"
FONT = "'JetBrains Mono','SF Mono','Fira Code',Consolas,'DejaVu Sans Mono',monospace"
LEVELS = ["#0e2a43", "#14586b", "#1f8a89", "#4fc4b0", "#a8f0dc"]

WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


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
            n = e["node"]["name"]
            slot = langs.setdefault(n, {"size": 0, "color": e["node"]["color"] or MUTED})
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
        # night-owl: heavier on weekday evenings, some dead days
        base = 0 if rnd.random() < 0.22 else rnd.randint(1, 14)
        days.append({"date": d.isoformat(), "count": base + (3 if d.weekday() in (1, 2, 3) else 0) * (base > 0)})
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
# helpers
# --------------------------------------------------------------------------
def fmt(n: int) -> str:
    if n >= 10_000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n:,}"


def svg(w: int, h: int, body: str, defs: str = "", title: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}" '
        f'font-family="{FONT}">\n<title>{escape(title)}</title>\n'
        f"<defs>{defs}</defs>\n{body}\n</svg>\n"
    )


def card(w: int, h: int, heading: str, inner: str, extra_defs: str = "") -> str:
    defs = (
        f'<linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{CARD}"/><stop offset="1" stop-color="{BG}"/></linearGradient>'
        f'<linearGradient id="bar" x1="0" x2="1"><stop offset="0" stop-color="{TEAL}"/>'
        f'<stop offset="1" stop-color="{PURPLE}"/></linearGradient>' + extra_defs
    )
    body = (
        f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="14" fill="url(#g)" stroke="{EDGE}"/>'
        f'<text x="22" y="34" fill="{TEAL}" font-size="13" font-weight="700" letter-spacing="1.5">'
        f"{escape(heading.upper())}</text>"
        f'<rect x="22" y="44" width="28" height="3" rx="1.5" fill="url(#bar)"/>' + inner
    )
    return svg(w, h, body, defs, heading)


def write(name: str, content: str) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / name).write_text(content, encoding="utf-8")
    print(f"wrote assets/{name} ({len(content) / 1024:.1f} KB)")


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


# --------------------------------------------------------------------------
# cards
# --------------------------------------------------------------------------
def stats_card(d: dict) -> str:
    items = [
        ("commits · 1y", d["commits"], TEAL), ("pull requests", d["prs"], PURPLE),
        ("issues", d["issues"], YELLOW), ("stars earned", d["stars"], PINK),
        ("followers", d["followers"], BLUE), ("public repos", d["repos"], TEAL),
    ]
    out = []
    for i, (label, val, color) in enumerate(items):
        x, y = 22 + (i % 2) * 190, 78 + (i // 2) * 38
        out.append(
            f'<circle cx="{x + 5}" cy="{y - 5}" r="4" fill="{color}"/>'
            f'<text x="{x + 18}" y="{y}" fill="{TEXT}" font-size="17" font-weight="700">{fmt(val)}</text>'
            f'<text x="{x + 18}" y="{y + 15}" fill="{MUTED}" font-size="11">{label}</text>'
        )
    return card(400, 200, "GitHub stats", "".join(out))


def streak_card(d: dict) -> str:
    cur, longest = streaks(d["days"])
    ratio = min(cur / max(longest, 1), 1)
    r, circ = 46, 2 * 3.14159265 * 46
    ring = (
        f'<g transform="translate(86 128)">'
        f'<circle r="{r}" fill="none" stroke="{EDGE}" stroke-width="9"/>'
        f'<circle r="{r}" fill="none" stroke="url(#bar)" stroke-width="9" stroke-linecap="round" '
        f'stroke-dasharray="{circ * ratio:.1f} {circ:.1f}" transform="rotate(-90)"/>'
        f'<text y="6" text-anchor="middle" fill="{TEXT}" font-size="26" font-weight="700">{cur}</text>'
        f'<text y="24" text-anchor="middle" fill="{MUTED}" font-size="10">day streak</text></g>'
    )
    side = (
        f'<text x="190" y="92" fill="{YELLOW}" font-size="22" font-weight="700">{longest}</text>'
        f'<text x="190" y="108" fill="{MUTED}" font-size="11">longest streak</text>'
        f'<text x="190" y="144" fill="{PURPLE}" font-size="22" font-weight="700">{fmt(d["total"])}</text>'
        f'<text x="190" y="160" fill="{MUTED}" font-size="11">contributions · last year</text>'
    )
    return card(400, 200, "Streak", ring + side)


def languages_card(d: dict) -> str:
    langs = sorted(d["langs"].items(), key=lambda kv: -kv[1]["size"])
    total = sum(v["size"] for _, v in langs) or 1
    top = langs[:6]
    rest = total - sum(v["size"] for _, v in top)
    rows = [(n, v["size"], v["color"]) for n, v in top]
    if rest > 0:
        rows.append(("Other", rest, MUTED))

    bar, x = [], 22.0
    width = 356
    for i, (_, size, color) in enumerate(rows):
        w = size / total * width
        bar.append(f'<rect x="{x:.1f}" y="62" width="{max(w - 2, 1):.1f}" height="10" rx="3" fill="{color}"/>')
        x += w
    legend = []
    for i, (name, size, color) in enumerate(rows):
        cx, cy = 22 + (i % 2) * 190, 102 + (i // 2) * 24
        legend.append(
            f'<circle cx="{cx + 4}" cy="{cy - 4}" r="4" fill="{color}"/>'
            f'<text x="{cx + 16}" y="{cy}" fill="{TEXT}" font-size="12">{escape(name)}</text>'
            f'<text x="{cx + 150}" y="{cy}" fill="{MUTED}" font-size="11" text-anchor="end">'
            f"{size / total * 100:.1f}%</text>"
        )
    return card(400, 200, "Top languages", "".join(bar + legend))


def weekday_card(d: dict) -> str:
    totals = weekday_totals(d["days"])
    peak = max(totals) or 1
    best = totals.index(max(totals))
    bars = []
    for i, t in enumerate(totals):
        h = max(t / peak * 80, 3)
        x = 30 + i * 49
        color = "url(#bar)" if i == best else LEVELS[2]
        bars.append(
            f'<rect x="{x}" y="{150 - h:.1f}" width="30" height="{h:.1f}" rx="5" fill="{color}"/>'
            f'<text x="{x + 15}" y="172" text-anchor="middle" fill="{TEXT if i == best else MUTED}" '
            f'font-size="11">{WEEKDAYS[i]}</text>'
        )
    note = f'<text x="378" y="34" text-anchor="end" fill="{MUTED}" font-size="11">peak: {WEEKDAYS[best]}</text>'
    return card(400, 200, "Weekly rhythm", "".join(bars) + note)


def activity_card(d: dict, span: int = 30) -> str:
    days = d["days"][-span:]
    w, h = 400, 200
    left, right, top, bottom = 40, 22, 66, 38
    pw, ph = w - left - right, h - top - bottom
    peak = max(max(x["count"] for x in days), 1)
    step = pw / (len(days) - 1)
    pts = [(left + i * step, top + ph - x["count"] / peak * ph) for i, x in enumerate(days)]

    # smooth path (catmull-rom -> bezier)
    def seg(i):
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, len(pts) - 1)]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, min(max(p1[1] + (p2[1] - p0[1]) / 6, top), top + ph))
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, min(max(p2[1] - (p3[1] - p1[1]) / 6, top), top + ph))
        return f"C{c1[0]:.1f},{c1[1]:.1f} {c2[0]:.1f},{c2[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}"

    line = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}" + "".join(seg(i) for i in range(len(pts) - 1))
    area = f"{line} L{pts[-1][0]:.1f},{top + ph} L{pts[0][0]:.1f},{top + ph} Z"

    grid = []
    for k in range(4):
        y = top + ph * k / 3
        val = round(peak * (1 - k / 3))
        grid.append(
            f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="{EDGE}" stroke-dasharray="3 5"/>'
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" fill="{MUTED}" font-size="10">{val}</text>'
        )
    labels = []
    for i in range(0, len(days), max(span // 5, 1)):
        date = dt.date.fromisoformat(days[i]["date"])
        labels.append(
            f'<text x="{pts[i][0]:.1f}" y="{h - 14}" text-anchor="middle" fill="{MUTED}" '
            f'font-size="10">{date.strftime("%b %d")}</text>'
        )
    hi = max(range(len(days)), key=lambda i: days[i]["count"])
    dot = (
        f'<circle cx="{pts[hi][0]:.1f}" cy="{pts[hi][1]:.1f}" r="4.5" fill="{YELLOW}" stroke="{BG}" stroke-width="2"/>'
        f'<text x="{pts[hi][0]:.1f}" y="{pts[hi][1] - 10:.1f}" text-anchor="middle" fill="{YELLOW}" '
        f'font-size="11" font-weight="700">{days[hi]["count"]}</text>'
    )
    defs = (
        f'<linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{TEAL}" stop-opacity=".35"/>'
        f'<stop offset="1" stop-color="{TEAL}" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="stroke" x1="0" x2="1"><stop offset="0" stop-color="{TEAL}"/>'
        f'<stop offset="1" stop-color="{PURPLE}"/></linearGradient>'
    )
    inner = (
        "".join(grid) + f'<path d="{area}" fill="url(#fill)"/>'
        f'<path d="{line}" fill="none" stroke="url(#stroke)" stroke-width="2.5" stroke-linejoin="round"/>'
        + dot + "".join(labels)
        + f'<text x="{w - 22}" y="34" text-anchor="end" fill="{MUTED}" font-size="11">'
        f"{span}d · {sum(x['count'] for x in days)} total</text>"
    )
    return card(w, h, "Activity", inner, defs)


def monthly_card(d: dict) -> str:
    months: dict[str, int] = {}
    for x in d["days"]:
        months[x["date"][:7]] = months.get(x["date"][:7], 0) + x["count"]
    keys = sorted(months)[-12:]
    peak = max(months[k] for k in keys) or 1
    best = max(keys, key=lambda k: months[k])
    out = []
    for i, k in enumerate(keys):
        hgt = max(months[k] / peak * 78, 3)
        x = 24 + i * 30
        color = "url(#bar)" if k == best else LEVELS[2]
        label = dt.date.fromisoformat(k + "-01").strftime("%b")[0]
        out.append(
            f'<rect x="{x}" y="{148 - hgt:.1f}" width="20" height="{hgt:.1f}" rx="4" fill="{color}"/>'
            f'<text x="{x + 10}" y="168" text-anchor="middle" fill="{TEXT if k == best else MUTED}" font-size="11">{label}</text>'
        )
    note = (f'<text x="378" y="34" text-anchor="end" fill="{MUTED}" font-size="11">'
            f'best: {dt.date.fromisoformat(best + "-01").strftime("%b")} · {months[best]}</text>')
    return card(400, 200, "12 months", "".join(out) + note)


# --------------------------------------------------------------------------
# static assets: hero + tech stack
# --------------------------------------------------------------------------
def hero() -> str:
    b64 = base64.b64encode((STATIC_SRC / "avatar.png").read_bytes()).decode()
    w, h = 640, 300
    defs = (
        f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{CARD}"/>'
        f'<stop offset="1" stop-color="{BG}"/></linearGradient>'
        f'<linearGradient id="name" x1="0" x2="1"><stop offset="0" stop-color="{TEAL}"/>'
        f'<stop offset="1" stop-color="{PURPLE}"/></linearGradient>'
        '<clipPath id="r"><rect width="640" height="300" rx="18"/></clipPath>'
        '<style>'
        '.cur{animation:blink 1s steps(1) infinite}'
        '@keyframes blink{50%{opacity:0}}'
        '.t{stroke-dasharray:420;stroke-dashoffset:420;animation:type 2.2s .3s steps(32) forwards}'
        '@keyframes type{to{stroke-dashoffset:0}}'
        '.fade{opacity:0;animation:in .8s ease forwards}'
        '@keyframes in{to{opacity:1}}'
        '.glow{animation:pulse 5s ease-in-out infinite}'
        '@keyframes pulse{50%{opacity:.55}}'
        '</style>'
    )
    # grid of faint dots for a "terminal graph paper" feel
    dots = "".join(
        f'<circle cx="{x}" cy="{y}" r="1" fill="{EDGE}"/>'
        for x in range(20, w, 30) for y in range(20, h, 30)
    )
    body = f"""<g clip-path="url(#r)">
<rect width="{w}" height="{h}" fill="url(#bg)"/>{dots}
<circle class="glow" cx="500" cy="150" r="150" fill="{PURPLE}" opacity=".16"/>
<circle class="glow" cx="120" cy="40" r="120" fill="{TEAL}" opacity=".10"/>
<image href="data:image/png;base64,{b64}" x="440" y="14" height="280" width="180" preserveAspectRatio="xMidYMax meet"/>
</g>
<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="18" fill="none" stroke="{EDGE}"/>
<text x="44" y="64" fill="{MUTED}" font-size="15" class="fade">~/mim-sad <tspan fill="{TEAL}">$</tspan> whoami</text>
<text x="44" y="116" fill="url(#name)" font-size="33" font-weight="800" class="fade">Mohammad Sadegh</text>
<text x="44" y="156" fill="url(#name)" font-size="33" font-weight="800" class="fade">Taghizadeh</text>
<text x="44" y="200" fill="{TEXT}" font-size="15" class="fade">Full-stack dev · Graphic designer</text>
<text x="44" y="240" fill="{YELLOW}" font-size="15">&gt; shipping AI-powered things<tspan class="cur" fill="{TEAL}">▌</tspan></text>
<text x="44" y="272" fill="{MUTED}" font-size="12" class="fade">python · js · c# · c++ · unity · design</text>"""
    return svg(w, h, body, defs, "Mohammad Sadegh Taghizadeh — developer and graphic designer")


STACK = [  # (label, icon key, tile fg)
    ("Python", "Python", "#fff"), ("JavaScript", "JavaScript", "#000"), ("C#", None, "#fff"),
    ("C++", "C++", "#fff"), ("Java", "Java", "#000"), ("HTML5", "HTML5", "#fff"),
    ("CSS3", "CSS3", "#fff"), ("React", "React", "#000"), ("Node.js", "Node.js", "#fff"),
    ("MongoDB", "MongoDB", "#fff"), ("Git", "Git", "#fff"), ("Linux", "Linux", "#000"),
    ("Unity", "Unity", "#fff"), ("Unreal", "Unreal", "#fff"), ("Colab", "Colab", "#000"),
    ("Photoshop", "Photoshop", "#001e36"), ("Illustrator", "Illustrator", "#330000"),
    ("AE", "After Effects", "#00005b"),
]
TILE_BG = {"Unity": "#555", "Unreal": "#2a2a2a", "C#": "#68217A"}


def tech_stack() -> str:
    icons = json.loads((ROOT / "scripts" / "icons.json").read_text())
    per_row, cw, ch, pad = 6, 80, 84, 10
    w = per_row * cw + pad * 2
    rows = -(-len(STACK) // per_row)
    h = rows * ch + pad * 2
    out = []
    for i, (label, key, fg) in enumerate(STACK):
        x, y = pad + (i % per_row) * cw, pad + (i // per_row) * ch
        bg = TILE_BG.get(label) or ("#" + icons[key]["color"] if key else CARD)
        # light brand colors get a dark glyph, dark ones a light glyph
        tile = (
            f'<g transform="translate({x + 18} {y})">'
            f'<rect width="44" height="44" rx="11" fill="{bg}"/>'
        )
        if key:
            tile += f'<path transform="translate(10 10)" d="{icons[key]["d"]}" fill="{fg}"/>'
        else:
            tile += f'<text x="22" y="29" text-anchor="middle" fill="{fg}" font-size="19" font-weight="800">C#</text>'
        tile += "</g>"
        out.append(
            tile + f'<text x="{x + 40}" y="{y + 64}" text-anchor="middle" fill="{TEXT}" font-size="11">{escape(label)}</text>'
        )
    return svg(w, h, "".join(out), "", "Tech stack")


def build_static() -> None:
    write("hero.svg", hero())
    write("stack.svg", tech_stack())


def build_dynamic(d: dict) -> None:
    write("stats.svg", stats_card(d))
    write("streak.svg", streak_card(d))
    write("languages.svg", languages_card(d))
    write("weekly.svg", weekday_card(d))
    write("activity.svg", activity_card(d))
    write("monthly.svg", monthly_card(d))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--static", action="store_true", help="only hero + tech stack")
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
