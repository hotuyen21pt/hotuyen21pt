#!/usr/bin/env python3
"""Render the profile cards as SVG files committed to this repo.

The public github-readme-stats / streak-stats / activity-graph deployments
answer 503 and 402, so nothing on the README is allowed to depend on them.
This script talks to the GitHub REST and GraphQL APIs itself and writes:

    assets/stats.svg             terminal telemetry panel  (REST)
    assets/top-langs.svg         language loadout          (REST)
    assets/contribution-jet.svg  contribution grid + jet

and rewrites the repository count in README.md so it cannot go stale.

    python scripts/gen_stats.py                 # works with no credentials
    GITHUB_TOKEN=... python scripts/gen_stats.py
    python scripts/gen_stats.py --fixture       # synthetic data into preview/

The contribution calendar comes from GraphQL when a token is available and
from the public contributions page otherwise, so the card renders either way.
An earlier version was GraphQL-only; the Actions GITHUB_TOKEN could not read
the calendar, the run failed, and the README was left pointing at a card that
had never been written.
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

USER = os.environ.get("PROFILE_USER", "hotuyen21pt")
TOKEN = os.environ.get("PROFILE_TOKEN") or os.environ.get("GITHUB_TOKEN")
ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = "--fixture" in sys.argv
# Synthetic runs render into preview/, which is gitignored. Pointing them at
# assets/ would overwrite real cards with invented numbers, and a rate-limited
# retry would then have no way to put the truth back.
ASSETS = ROOT / ("preview" if FIXTURE else "assets")

# Vendored or generated output rather than code I wrote; counting it would make
# the card claim a language I don't work in. Notebooks, HTML, CSS and TeX are
# excluded too: notebook JSON and exported reports are bulky, so by bytes they
# dwarf the Python, Go and TypeScript the tech stack is actually built on.
EXCLUDE_LANGS = {"Mako", "Batchfile", "Makefile", "Jupyter Notebook", "HTML", "CSS", "TeX"}

LANG_COLORS = {
    "Python": "#3572A5",
    "Jupyter Notebook": "#DA5B0B",
    "Go": "#00ADD8",
    "TypeScript": "#3178C6",
    "JavaScript": "#F1E05A",
    "HTML": "#E34C26",
    "CSS": "#663399",
    "Dockerfile": "#384D54",
    "PowerShell": "#012456",
    "Shell": "#89E051",
    "TeX": "#3D6117",
    "C++": "#F34B7D",
    "Java": "#B07219",
    "Rust": "#DEA584",
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Light defaults, overridden under a dark colour scheme. Every card shares
# these names so the three of them stay in one visual family.
THEME = """
    svg {
      --bg:#FFFFFF; --panel:#F6F8FA; --bd:#D8DEE4; --tx:#1F2328; --mu:#636C76;
      --ac:#0B6FD4; --hi:#6A3DE8;
      --l0:#E7ECF2; --l1:#BDDCF5; --l2:#6FB7EB; --l3:#2E8FD6; --l4:#0B5FB8;
    }
    @media (prefers-color-scheme: dark) {
      svg {
        --bg:#0D1117; --panel:#111823; --bd:#1E3A52; --tx:#C9D1D9; --mu:#8B949E;
        --ac:#36BCF7; --hi:#9D7BFF;
        --l0:#161B22; --l1:#0E3A5C; --l2:#1569A3; --l3:#2E9BE0; --l4:#7FE3FF;
      }
    }
"""

BASE_CSS = """
    .mono { font: 400 12.5px 'JetBrains Mono','Cascadia Code','Fira Code',Consolas,'Liberation Mono',monospace }
    .cmd  { font: 400 11px 'JetBrains Mono','Cascadia Code',Consolas,monospace; fill: var(--mu) }
    .k    { fill: var(--mu) }
    .v    { fill: var(--tx); font-weight: 700 }
    .ac   { fill: var(--ac) }
    .s    { font: 400 10.5px 'JetBrains Mono','Cascadia Code',Consolas,monospace; fill: var(--mu) }
    .big  { font: 700 17px 'Segoe UI',Ubuntu,-apple-system,sans-serif; fill: var(--ac) }
    .rise { opacity:0; animation: rise .5s cubic-bezier(.2,.8,.2,1) both }
    @keyframes rise { from { opacity:0; transform: translateY(6px) } to { opacity:1; transform:none } }
    .blink { animation: blink 1.1s steps(1) infinite }
    @keyframes blink { 0%,50% { opacity:1 } 51%,100% { opacity:0 } }
    @media (prefers-reduced-motion: reduce) {
      .rise,.blink,.wipe,.shine,.fly,.col,.beam { animation: none !important; opacity: 1 }
      .wipe { width: 100% } .shine,.beam { display: none }
    }
"""


# ---------------------------------------------------------------- API access

def api(path: str):
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-profile-stats",
    })
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"GitHub API {exc.code} on {url}: {exc.read()[:200]!r}")


GQL = """
query($login:String!) {
  user(login:$login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionCount } }
      }
    }
  }
}
"""


TD_RE = re.compile(r'<td[^>]*class="[^"]*ContributionCalendar-day[^"]*"[^>]*>')
TIP_RE = re.compile(r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>')
ATTR_RE = re.compile(r'(data-date|data-level|id)="([^"]*)"')
COUNT_RE = re.compile(r"^(?:(\d+)|No)\s+contribution")


def html_calendar():
    """The same twelve months, scraped from the public contributions page.

    GraphQL is the better source but it refuses anonymous callers, which makes
    the card depend on a secret the repo may not have. This page is public, is
    the one GitHub renders on the profile itself, and needs no token - so the
    card can never silently vanish for want of a credential.
    """
    url = f"https://github.com/users/{USER}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": f"{USER}-profile-stats"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            page = resp.read().decode("utf-8", "replace")
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"! contributions page unreachable: {exc}")
        return None

    tips = {cell: text for cell, text in TIP_RE.findall(page)}
    days = {}
    for tag in TD_RE.findall(page):
        attrs = dict(ATTR_RE.findall(tag))
        iso = attrs.get("data-date")
        if not iso:
            continue
        m = COUNT_RE.match(tips.get(attrs.get("id", ""), ""))
        days[iso] = int(m.group(1)) if m and m.group(1) else 0

    if not days:
        print("! contributions page carried no day cells - markup may have changed")
        return None

    # Re-shape into the week/day nesting the GraphQL reply uses, so the card
    # renderer never has to know which source it got.
    weeks, week = [], []
    for iso in sorted(days):
        d = date.fromisoformat(iso)
        weekday = (d.weekday() + 1) % 7          # 0 = Sunday, as GitHub counts
        if weekday == 0 and week:
            weeks.append({"contributionDays": week})
            week = []
        week.append({"date": iso, "weekday": weekday, "contributionCount": days[iso]})
    if week:
        weeks.append({"contributionDays": week})

    print(f"read {len(days)} days from the public contributions page")
    return {"totalContributions": sum(days.values()), "weeks": weeks}


def graphql_calendar():
    """Twelve months of contributions, or None when the token cannot see them."""
    if not TOKEN:
        return None
    body = json.dumps({"query": GQL, "variables": {"login": USER}}).encode()
    req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": f"{USER}-profile-stats",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        print(f"! GraphQL {exc.code}: {exc.read()[:200]!r} - skipping the contribution card")
        return None
    if payload.get("errors"):
        print(f"! GraphQL errors: {payload['errors']} - skipping the contribution card")
        return None
    return payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]


# ------------------------------------------------------------------ fixtures

def fixture_stats() -> dict:
    return {"repos": 24, "stars": 7, "forks": 3, "followers": 11,
            "langs": {"Python": 4_100_000, "Jupyter Notebook": 2_300_000,
                      "TypeScript": 410_000, "Go": 260_000, "TeX": 180_000,
                      "HTML": 90_000, "CSS": 52_000, "Shell": 21_000},
            "kb": 512_000, "since": 2021, "years": 4}


def fixture_calendar() -> dict:
    rng = random.Random(7)
    end = date.today()
    start = end - timedelta(days=364)
    start -= timedelta(days=(start.weekday() + 1) % 7)  # back to a Sunday
    weeks, day, total = [], start, 0
    while day <= end:
        days = []
        for _ in range(7):
            n = 0 if rng.random() < 0.34 else rng.randint(1, 18)
            if day > end:
                n = 0
            days.append({"date": day.isoformat(), "weekday": (day.weekday() + 1) % 7,
                         "contributionCount": n})
            total += n
            day += timedelta(days=1)
        weeks.append({"contributionDays": days})
    return {"totalContributions": total, "weeks": weeks}


# -------------------------------------------------------------- data shaping

def collect() -> dict:
    user = api(f"/users/{USER}")
    repos, page = [], 1
    while True:
        batch = api(f"/users/{USER}/repos?per_page=100&page={page}&type=owner")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    own = [r for r in repos if not r["fork"]]
    langs: dict[str, int] = {}
    for r in own:
        for name, count in api(r["languages_url"]).items():
            if name not in EXCLUDE_LANGS:
                langs[name] = langs.get(name, 0) + count

    created = datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
    return {
        "repos": len(own),
        "stars": sum(r["stargazers_count"] for r in own),
        "forks": sum(r["forks_count"] for r in own),
        "followers": user["followers"],
        "langs": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "kb": sum(r["size"] for r in own),
        "since": created.year,
        "years": max(1, (datetime.now(timezone.utc) - created).days // 365),
    }


def flatten(cal: dict) -> list[dict]:
    today = date.today().isoformat()
    return [d for w in cal["weeks"] for d in w["contributionDays"] if d["date"] <= today]


def streaks(days: list[dict]) -> dict:
    best = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] else 0
        best = max(best, run)

    # A quiet today does not break the streak until the day is over.
    tail = days[:-1] if days and days[-1]["contributionCount"] == 0 else days
    current = 0
    for d in reversed(tail):
        if not d["contributionCount"]:
            break
        current += 1

    peak = max(days, key=lambda d: d["contributionCount"]) if days else {"date": "-", "contributionCount": 0}
    active = sum(1 for d in days if d["contributionCount"])
    return {"current": current, "longest": best, "peak": peak, "active": active}


def levels(days: list[dict]) -> dict[str, int]:
    """Bucket each day 0-4 against the quartiles of its own non-empty days."""
    hot = sorted(d["contributionCount"] for d in days if d["contributionCount"])
    if not hot:
        return {d["date"]: 0 for d in days}
    q = [hot[int(len(hot) * f)] for f in (0.25, 0.55, 0.85)]
    out = {}
    for d in days:
        n = d["contributionCount"]
        out[d["date"]] = 0 if n == 0 else 1 + sum(n > t for t in q)
    return out


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ----------------------------------------------------------------- SVG frame

def window(width: int, height: int, title: str, command: str, body: str, extra_css: str = "") -> str:
    """A terminal-style panel: title bar, traffic lights, prompt, then body."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">
  <style>{THEME}{BASE_CSS}{extra_css}</style>
  <defs>
    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="var(--ac)"/><stop offset="100%" stop-color="var(--hi)"/>
    </linearGradient>
    <clipPath id="card"><rect x="0" y="0" width="{width}" height="{height}" rx="12"/></clipPath>
  </defs>
  <g clip-path="url(#card)">
    <rect width="{width}" height="{height}" fill="var(--bg)"/>
    <rect width="{width}" height="34" fill="var(--panel)"/>
    <rect y="33" width="{width}" height="1" fill="var(--bd)"/>
    <rect width="{width}" height="2" fill="url(#edge)"/>
    <circle cx="20" cy="18" r="4" fill="#FF5F57"/>
    <circle cx="34" cy="18" r="4" fill="#FEBC2E"/>
    <circle cx="48" cy="18" r="4" fill="#28C840"/>
    <text x="66" y="22" class="cmd">{esc(command)}</text>
{body}
  </g>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="none" stroke="var(--bd)"/>
</svg>
"""


# ------------------------------------------------------------------ the cards

STATS_MIN_H = 62 + 5 * 25 + 4 + 42     # five rows, the footer line and the caret


def stats_card(d: dict, height: int) -> str:
    """Overview card, drawn at `height` so it pairs with the languages card.

    Stars, forks and followers are left out on purpose: on a research profile
    they are small numbers that say little about the work.
    """
    top = next(iter(d["langs"]), "-")
    rows = [
        ("public repos",   str(d["repos"])),
        ("languages",      str(len(d["langs"]))),
        ("top language",   top),
        ("code on github", f"{d['kb'] / 1024:.0f} MB"),
        ("member since",   f"{d['since']} - {d['years']}y"),
    ]
    w, out = 440, []
    for i, (key, val) in enumerate(rows):
        y = 62 + i * 25
        kw = 10 + len(key) * 7.6          # where the key text ends
        vw = len(val) * 7.6
        out.append(
            f'    <g class="rise" style="animation-delay:{0.06 * i:.2f}s">'
            f'<text x="24" y="{y}" class="mono ac">&#9656;</text>'
            f'<text x="42" y="{y}" class="mono k">{esc(key)}</text>'
            f'<line x1="{42 + kw:.0f}" y1="{y - 4}" x2="{w - 26 - vw:.0f}" y2="{y - 4}" '
            f'stroke="var(--bd)" stroke-width="1" stroke-dasharray="1 4"/>'
            f'<text x="{w - 24}" y="{y}" class="mono v" text-anchor="end">{esc(val)}</text></g>'
        )
    foot = height - 42
    out.append(f'    <text x="24" y="{foot}" class="s"># regenerated daily - no third-party service</text>')
    out.append(f'    <rect class="blink" x="24" y="{foot + 12}" width="8" height="14" fill="var(--ac)"/>')
    return window(w, height, "Overview", f"~/{USER} $ gh stats --me", "\n".join(out))


# One row per language, each element in its own x-band. A two-column legend
# packs a name and its percentage into ~190px, which "Jupyter Notebook" (120px
# at 12.5px mono) plus "43.2%" overruns - the labels collide. Giving every
# field a fixed band makes that collision impossible rather than unlikely.
ROW_SWATCH = 24
ROW_NAME = 41
ROW_TRACK = 208
ROW_TRACK_W = 150
ROW_VALUE = 416
NAME_CHARS = 20
MONO_ADV = 7.5          # widest advance among the fonts in the mono stack


def _check_bands() -> None:
    """Fail the build, not the reader, if the row bands ever start to overlap.

    Twice now a label has been truncated or overprinted because a width was
    estimated by eye. These are the two gaps that matter; both are arithmetic.
    """
    name_end = ROW_NAME + NAME_CHARS * MONO_ADV
    value_start = ROW_VALUE - len("100.0%") * MONO_ADV
    assert ROW_TRACK - name_end >= 8, f"name band overruns the track by {name_end - ROW_TRACK:.1f}px"
    assert value_start - (ROW_TRACK + ROW_TRACK_W) >= 8, "track overruns the percentage column"


def langs_height(n: int) -> int:
    """Height of the languages card for n rows (bar at 58, rows from 104)."""
    return 58 + 46 + (n - 1) * 25 + 26


def langs_card(d: dict, height: int, top: int = 8) -> str:
    _check_bands()
    items = list(d["langs"].items())[:top]
    total = sum(v for _, v in items) or 1
    peak = max(v for _, v in items) or 1
    w = 440
    bar_x, bar_w, bar_y = 24, w - 48, 58

    css = """
    .wipe { animation: wipe 1.1s cubic-bezier(.2,.8,.2,1) both }
    @keyframes wipe { from { width: 0 } to { width: %dpx } }
    .grow { transform-origin: %dpx 0; animation: grow .9s cubic-bezier(.2,.8,.2,1) both }
    @keyframes grow { from { transform: scaleX(0) } to { transform: scaleX(1) } }
    @media (prefers-reduced-motion: reduce) { .grow { animation: none } }
""" % (bar_w, ROW_TRACK)

    # Share bar: a 2px surface gap keeps adjacent segments from reading as one.
    segs, x = [], float(bar_x)
    for i, (name, count) in enumerate(items):
        seg = bar_w * count / total
        r = 7 if i in (0, len(items) - 1) else 0
        segs.append(f'      <rect x="{x:.1f}" y="{bar_y}" width="{max(seg - 2, 1):.1f}" height="14" '
                    f'rx="{r}" fill="{LANG_COLORS.get(name, "#6E7681")}"/>')
        x += seg

    bar = (
        f'    <defs><clipPath id="barclip">'
        f'<rect class="wipe" x="{bar_x}" y="{bar_y}" width="0" height="14" rx="7"/></clipPath></defs>\n'
        f'    <g clip-path="url(#barclip)">\n' + "\n".join(segs) + "\n    </g>"
    )

    row_y, step = bar_y + 46, 25
    rows = []
    for i, (name, count) in enumerate(items):
        cy = row_y + i * step
        colour = LANG_COLORS.get(name, "#6E7681")
        label = name if len(name) <= NAME_CHARS else name[:NAME_CHARS - 1] + "…"
        fill_w = ROW_TRACK_W * count / peak
        rows.append(
            f'    <g class="rise" style="animation-delay:{0.55 + 0.05 * i:.2f}s">'
            f'<rect x="{ROW_SWATCH}" y="{cy - 9}" width="9" height="9" rx="2" fill="{colour}"/>'
            f'<text x="{ROW_NAME}" y="{cy}" class="mono k">{esc(label)}</text>'
            f'<rect x="{ROW_TRACK}" y="{cy - 7}" width="{ROW_TRACK_W}" height="6" rx="3" '
            f'fill="var(--bd)" opacity=".55"/>'
            f'<rect class="grow" style="animation-delay:{0.6 + 0.05 * i:.2f}s" '
            f'x="{ROW_TRACK}" y="{cy - 7}" width="{fill_w:.1f}" height="6" rx="3" fill="{colour}"/>'
            f'<text x="{ROW_VALUE}" y="{cy}" class="mono v" text-anchor="end">'
            f'{100.0 * count / total:.1f}%</text></g>'
        )

    return window(w, height, "Most used languages", f"~/{USER} $ gh loadout --languages",
                  bar + "\n" + "\n".join(rows), css)


CELL, GAP = 12, 3
STEP = CELL + GAP
JET_W = 880
GX, GY = 56, 70                 # grid origin
FLY_FROM, FLY_TO = -70, JET_W + 80
FLY_SECS = 9.0
BEAM = 58                       # how far the beam reaches ahead of the nose


def jet_card(cal: dict) -> str:
    days = flatten(cal)
    st = streaks(days)
    lv = levels(days)
    by_date = {d["date"]: d for d in days}

    weeks = cal["weeks"][-53:]
    grid_h = 7 * STEP - GAP
    mid = GY + grid_h / 2

    # Month ruler: label the week in which the month turns over. The opening
    # week is skipped unless it genuinely starts its month, so the ruler never
    # repeats the same name twice at the left edge.
    ruler, seen = [], None
    for i, wk in enumerate(weeks):
        first = date.fromisoformat(wk["contributionDays"][0]["date"])
        if first.month != seen:
            if seen is not None or first.day <= 7:
                ruler.append(f'    <text x="{GX + i * STEP}" y="{GY - 12}" class="s">'
                             f'{MONTHS[first.month - 1]}</text>')
            seen = first.month

    rows = [f'    <text x="{GX - 10}" y="{GY + r * STEP + 10}" class="s" text-anchor="end">{lbl}</text>'
            for r, lbl in ((1, "Mon"), (3, "Wed"), (5, "Fri"))]

    cols = []
    for i, wk in enumerate(weeks):
        x = GX + i * STEP
        # The beam front reaches this column at t; the flash is keyed to it.
        t = FLY_SECS * (x + CELL / 2 - BEAM - FLY_FROM) / (FLY_TO - FLY_FROM)
        cells = []
        for d in wk["contributionDays"]:
            iso = d["date"]
            if iso not in by_date:
                continue
            # No per-cell <title>: GitHub renders this file inside an <img>,
            # where tooltips never fire, and 365 of them double the file size.
            y = GY + d["weekday"] * STEP
            cells.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="3" '
                f'fill="var(--l{lv[iso]})"/>'
            )
        if cells:
            cols.append(f'    <g class="col" style="animation-delay:{0.012 * i:.2f}s,{max(t, 0):.2f}s">'
                        + "".join(cells) + "</g>")

    jet = f"""    <g transform="translate(0,{mid:.0f})">
      <g class="fly">
        <rect class="beam" x="14" y="-1.6" width="{BEAM}" height="3.2" rx="1.6" fill="url(#beamg)"/>
        <rect x="-34" y="-2.5" width="26" height="5" rx="2.5" fill="url(#trail)"/>
        <path d="M18,0 L-8,-7 L-2,0 L-8,7 Z" fill="var(--ac)"/>
        <path d="M-2,-3.5 L-15,-13 L-6,-3.5 Z" fill="var(--hi)"/>
        <path d="M-2,3.5 L-15,13 L-6,3.5 Z" fill="var(--hi)"/>
        <circle cx="-6" cy="0" r="3" fill="#FFFFFF" opacity=".92"/>
      </g>
    </g>"""

    tiles = [
        (f'{cal["totalContributions"]:,}', "contributions - 12 mo"),
        (f'{st["current"]}', "day current streak"),
        (f'{st["longest"]}', "day longest streak"),
        (f'{st["peak"]["contributionCount"]}', f'busiest day - {st["peak"]["date"]}'),
    ]
    base = GY + grid_h + 44
    stat = []
    for i, (val, lbl) in enumerate(tiles):
        x = GX + i * 206
        stat.append(
            f'    <g class="rise" style="animation-delay:{0.9 + 0.08 * i:.2f}s">'
            f'<rect x="{x - 2}" y="{base - 22}" width="3" height="30" rx="1.5" fill="var(--ac)" opacity=".7"/>'
            f'<text x="{x + 12}" y="{base}" class="big">{esc(val)}</text>'
            f'<text x="{x + 12}" y="{base + 16}" class="s">{esc(lbl)}</text></g>'
        )

    css = """
    .col { opacity:0; animation: boot .45s ease-out both, zap %.1fs linear infinite }
    @keyframes boot { from { opacity:0; transform: translateY(5px) } to { opacity:1; transform:none } }
    @keyframes zap { 0%% { filter: brightness(2.7) } 5%% { filter:none } 100%% { filter:none } }
    .fly { animation: fly %.1fs linear infinite }
    @keyframes fly { from { transform: translateX(%dpx) } to { transform: translateX(%dpx) } }
""" % (FLY_SECS, FLY_SECS, FLY_FROM, FLY_TO)

    defs = """    <defs>
      <linearGradient id="beamg" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="var(--ac)" stop-opacity=".95"/>
        <stop offset="70%" stop-color="var(--hi)" stop-opacity=".55"/>
        <stop offset="100%" stop-color="var(--hi)" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="trail" x1="1" y1="0" x2="0" y2="0">
        <stop offset="0%" stop-color="var(--ac)" stop-opacity=".8"/>
        <stop offset="100%" stop-color="var(--ac)" stop-opacity="0"/>
      </linearGradient>
    </defs>"""

    body = "\n".join([defs, *ruler, *rows, *cols, jet, *stat])
    return window(JET_W, base + 34, "Contribution activity",
                  f"~/{USER} $ gh contributions --last 12mo --render jet", body, css)


# ------------------------------------------------------------- track record

# Facts about the work rather than the account, edited by hand when they change:
# paper reproductions (CXR-VQA, S2IT, Tree-CoT-RT), tests (180 EvidenceKD + 95
# ASQP baselines) and PRISM's review corpus. Only the repository count is live.
TRACK_STATIC = [("3", "paper reproductions"), ("275+", "tests passing"),
                ("1.95M", "reviews analysed")]


ODO_ADV = 15.0          # advance of one glyph in the odometer (textLength pins it)
ODO_LINE = 30           # height of one digit cell in a rolling column
ODO_LOOP = 10           # seconds: roll in, hold, roll again


def _odometer(val: str, x: float, y: float, acc: str, idx: int) -> tuple[str, str]:
    """Draw `val` with each digit on a column of 0-9 twice over that rolls up
    to its value, odometer style. Non-digits (".", "M", "+") stand still.
    Returns (markup, clip-path defs)."""
    top = y - 24                                   # top of the digit window
    parts, cx = [], x
    for j, ch in enumerate(val):
        if ch.isdigit():
            d = int(ch)
            column = "".join(
                f'<text x="{cx:.1f}" y="{y + k * ODO_LINE}" class="num" fill="{acc}" textLength="{ODO_ADV - 1:.0f}" '
                f'lengthAdjust="spacingAndGlyphs">{k % 10}</text>' for k in range(20))
            # Land on the second pass so every digit spins at least once.
            to = -(10 + d) * ODO_LINE
            parts.append(f'<g class="roll" style="--to:{to}px;animation-delay:{0.15 + idx * 0.12 + j * 0.08:.2f}s">'
                         f'{column}</g>')
        else:
            parts.append(f'<text x="{cx:.1f}" y="{y}" class="num" fill="{acc}">{esc(ch)}</text>')
        cx += ODO_ADV
    clip = (f'<clipPath id="odo{idx}"><rect x="{x - 2:.1f}" y="{top}" width="{len(val) * ODO_ADV + 4:.0f}" '
            f'height="{ODO_LINE}"/></clipPath>')
    return f'<g clip-path="url(#odo{idx})">{"".join(parts)}</g>', clip


def track_card(repos: int) -> str:
    """Four headline numbers whose digits roll in like an odometer, re-rolling
    every ODO_LOOP seconds."""
    items = [(str(repos), "public repositories")] + TRACK_STATIC
    w, h, gap = 830, 78, 12
    bw = (w - 2 - gap * (len(items) - 1)) / len(items)
    accents = ["var(--ac)", "var(--hi)"]
    boxes, clips = [], []
    for i, (val, label) in enumerate(items):
        x = 1 + i * (bw + gap)
        acc = accents[i % len(accents)]
        num, clip = _odometer(val, x + 20, 42, acc, i)
        clips.append(clip)
        boxes.append(
            f'  <g class="pop" style="animation-delay:{0.1 + i * 0.1:.2f}s">'
            f'<rect x="{x:.1f}" y="1" width="{bw:.1f}" height="{h - 2}" rx="12" fill="var(--panel)" '
            f'stroke="var(--bd)"/>'
            f'<rect x="{x:.1f}" y="14" width="3" height="{h - 28}" rx="1.5" fill="{acc}"/>'
            f'{num}<text x="{x + 20:.1f}" y="62" class="lbl">{esc(label)}</text></g>'
        )
    css = """
    .num { font: 800 24px 'JetBrains Mono','Cascadia Code',Consolas,monospace }
    .lbl { font: 500 10.5px 'JetBrains Mono','Cascadia Code',Consolas,monospace; fill: var(--mu); letter-spacing: .4px }
    .pop { opacity:0; animation: pop .55s cubic-bezier(.22,1,.36,1) both }
    @keyframes pop { from { opacity:0; transform: translateY(6px) } to { opacity:1; transform:none } }
    .roll { animation: roll %ds cubic-bezier(.16,1,.3,1) infinite both }
    @keyframes roll { 0%% { transform: none } 22%%,88%% { transform: translateY(var(--to)) } 100%% { transform: translateY(var(--to)) } }
    @media (prefers-reduced-motion: reduce) {
      .pop { animation: none; opacity: 1 } .roll { animation: none; transform: translateY(var(--to)) }
    }
""" % ODO_LOOP
    label = " · ".join(f"{v} {l}" for v, l in items)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{esc(label)}">\n'
            f'  <defs>{"".join(clips)}</defs>\n'
            f'  <style>{THEME}{css}  </style>\n' + "\n".join(boxes) + "\n</svg>\n")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    data = fixture_stats() if FIXTURE else collect()
    # Filter here as well as in collect(), so fixture renders match real ones.
    data["langs"] = {k: v for k, v in data["langs"].items() if k not in EXCLUDE_LANGS}
    out = ASSETS.name
    # The overview and languages cards sit side by side, so both share the
    # languages card's height.
    pair_h = max(langs_height(min(8, len(data["langs"]))), STATS_MIN_H)
    (ASSETS / "stats.svg").write_text(stats_card(data, pair_h), encoding="utf-8")
    (ASSETS / "top-langs.svg").write_text(langs_card(data, pair_h), encoding="utf-8")
    (ASSETS / "track.svg").write_text(track_card(data["repos"]), encoding="utf-8")
    print(f"wrote {out}/stats.svg, {out}/top-langs.svg and {out}/track.svg")

    jet = ASSETS / "contribution-jet.svg"
    if FIXTURE:
        cal = fixture_calendar()
    else:
        cal = graphql_calendar() or html_calendar()
    missing = False
    if cal:
        jet.write_text(jet_card(cal), encoding="utf-8")
        print(f"wrote {out}/contribution-jet.svg ({cal['totalContributions']:,} contributions)")
    elif jet.exists():
        print("  keeping the previous contribution card")
    else:
        # The README links this card by relative path, so a missing file is a
        # broken image on the profile. That has to fail the run - but only
        # after the other cards are written, so a calendar outage never costs
        # us the stats refresh too.
        missing = True

    for name, count in list(data["langs"].items())[:8]:
        print(f"  {name:<18} {count:>10,} bytes")

    if missing:
        sys.exit("\nthe contribution card has never been rendered and the calendar is "
                 "unreachable - set PROFILE_TOKEN to a PAT with read:user")


if __name__ == "__main__":
    main()
