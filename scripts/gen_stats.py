#!/usr/bin/env python3
"""Render the profile stat cards as SVG files committed to this repo.

The public github-readme-stats / trophy deployments answer 503 and 402, so the
README cannot depend on them. This script talks to the GitHub REST API itself
and writes assets/stats.svg and assets/top-langs.svg, which the README embeds
by relative path. .github/workflows/update-stats.yml re-runs it on every push
and once a day.

    python scripts/gen_stats.py            # unauthenticated, 60 req/h
    GITHUB_TOKEN=... python scripts/gen_stats.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

USER = os.environ.get("PROFILE_USER", "hotuyen21pt")
ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# Vendored or generated output rather than code I wrote; counting it would make
# the card claim a language I don't work in.
EXCLUDE_LANGS = {"Mako", "Batchfile", "Makefile"}

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

# Light defaults, overridden under a dark colour scheme.
THEME = """
    svg { --bg:#FFFFFF; --bd:#D8DEE4; --tx:#1F2328; --mu:#636C76; --ac:#0B6FD4; --hi:#7C4DFF; }
    @media (prefers-color-scheme: dark) {
      svg { --bg:#0D1117; --bd:#1E3A52; --tx:#C9D1D9; --mu:#8B949E; --ac:#36BCF7; --hi:#9D7BFF; }
    }
"""

MOTION = """
    .rise { opacity:0; animation: rise .55s cubic-bezier(.2,.8,.2,1) both; }
    @keyframes rise { from { opacity:0; transform: translateY(8px) } to { opacity:1; transform:none } }
    @media (prefers-reduced-motion: reduce) {
      .rise { animation:none; opacity:1 } .wipe { animation:none; width:100% } .shine { display:none }
    }
"""


def api(path: str):
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-profile-stats",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"GitHub API {exc.code} on {url}: {exc.read()[:200]!r}")


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


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def frame(width: int, height: int, title: str, body: str, extra_css: str = "") -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">
  <style>{THEME}{MOTION}{extra_css}
    .t {{ font: 700 16px 'Segoe UI', Ubuntu, -apple-system, sans-serif; fill: var(--ac); letter-spacing:.3px }}
    .k {{ font: 400 14px 'Segoe UI', Ubuntu, -apple-system, sans-serif; fill: var(--tx) }}
    .v {{ font: 700 14px 'Segoe UI', Ubuntu, -apple-system, sans-serif; fill: var(--ac) }}
    .s {{ font: 400 11px 'Segoe UI', Ubuntu, -apple-system, sans-serif; fill: var(--mu) }}
  </style>
  <defs>
    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="var(--ac)"/><stop offset="100%" stop-color="var(--hi)"/>
    </linearGradient>
  </defs>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="var(--bg)" stroke="var(--bd)"/>
  <rect x="0" y="0" width="{width}" height="3" rx="1.5" fill="url(#edge)"/>
  <text x="24" y="38" class="t">{esc(title)}</text>
{body}
</svg>
"""


def stats_card(d: dict) -> str:
    rows = [
        ("Public repositories", str(d["repos"])),
        ("Stars earned", str(d["stars"])),
        ("Forks", str(d["forks"])),
        ("Followers", str(d["followers"])),
        ("Languages in use", str(len(d["langs"]))),
        ("Code on GitHub", f"{d['kb'] / 1024:.0f} MB"),
        ("Member since", f"{d['since']} · {d['years']} yrs"),
    ]
    out = []
    for i, (key, val) in enumerate(rows):
        y = 72 + i * 26
        out.append(
            f'  <g class="rise" style="animation-delay:{0.07 * i:.2f}s">'
            f'<circle cx="28" cy="{y - 5}" r="2.5" fill="var(--ac)" opacity=".55"/>'
            f'<text x="40" y="{y}" class="k">{esc(key)}</text>'
            f'<text x="376" y="{y}" class="v" text-anchor="end">{esc(val)}</text></g>'
        )
    foot = 72 + len(rows) * 26 + 6
    out.append(f'  <text x="24" y="{foot}" class="s">across {d["repos"]} source repositories · regenerated daily</text>')
    return frame(400, foot + 18, "Overview", "\n".join(out))


def langs_card(d: dict, top: int = 8) -> str:
    items = list(d["langs"].items())[:top]
    total = sum(v for _, v in items) or 1
    bar_x, bar_w, bar_y = 24, 352, 56

    css = """
    .wipe { animation: wipe 1.1s cubic-bezier(.2,.8,.2,1) both; }
    @keyframes wipe { from { width: 0 } to { width: 352px } }
    .shine { animation: shine 3.6s ease-in-out 1.2s infinite; }
    @keyframes shine { 0% { transform: translateX(-90px) } 60%,100% { transform: translateX(380px) } }
"""
    segs, x = [], float(bar_x)
    for i, (name, count) in enumerate(items):
        w = bar_w * count / total
        r = 6 if i in (0, len(items) - 1) else 0
        segs.append(f'      <rect x="{x:.1f}" y="{bar_y}" width="{w:.1f}" height="12" rx="{r}" '
                    f'fill="{LANG_COLORS.get(name, "#6E7681")}"/>')
        x += w

    bar = (
        f'  <defs><clipPath id="barclip"><rect class="wipe" x="{bar_x}" y="{bar_y}" width="0" height="12" rx="6"/></clipPath>\n'
        f'    <linearGradient id="gloss" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0%" stop-color="#fff" stop-opacity="0"/>'
        f'<stop offset="50%" stop-color="#fff" stop-opacity=".55"/>'
        f'<stop offset="100%" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>\n'
        f'  <g clip-path="url(#barclip)">\n' + "\n".join(segs) + "\n"
        f'    <rect class="shine" x="{bar_x}" y="{bar_y}" width="80" height="12" fill="url(#gloss)"/>\n'
        f'  </g>'
    )

    col_x, row_y = [24, 212], bar_y + 36
    legend = []
    for i, (name, count) in enumerate(items):
        cx, cy = col_x[i % 2], row_y + (i // 2) * 24
        legend.append(
            f'  <g class="rise" style="animation-delay:{0.9 + 0.06 * i:.2f}s">'
            f'<circle cx="{cx + 5}" cy="{cy - 4}" r="5" fill="{LANG_COLORS.get(name, "#6E7681")}"/>'
            f'<text x="{cx + 17}" y="{cy}" class="k">{esc(name)}</text>'
            f'<text x="{cx + 156}" y="{cy}" class="v" text-anchor="end">{100.0 * count / total:.1f}%</text></g>'
        )

    height = row_y + ((len(items) + 1) // 2) * 24 + 14
    return frame(400, height, "Most used languages", bar + "\n" + "\n".join(legend), css)


def main() -> None:
    data = collect()
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "stats.svg").write_text(stats_card(data), encoding="utf-8")
    (ASSETS / "top-langs.svg").write_text(langs_card(data), encoding="utf-8")
    print(f"wrote assets/stats.svg and assets/top-langs.svg for {USER}")
    for name, count in list(data["langs"].items())[:8]:
        print(f"  {name:<18} {count:>10,} bytes")


if __name__ == "__main__":
    main()
