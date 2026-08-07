#!/usr/bin/env python3
"""
update.py — self-updating GitHub profile generator.

Тянет реальные данные из GitHub API и перегенерирует SVG-ассеты
(stats / heatmap / languages) в единой дизайн-системе профиля,
затем обновляет AUTO-секцию README.md.

Usage:
    python update.py                          # anonymous (60 req/h)
    GITHUB_TOKEN=ghp_... python update.py     # полный календарь контрибуций

Project #1 of KeelBismarck. Hand-tuned, no templates.
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import requests
from github import Auth, Github

# ── config ────────────────────────────────────────────────────────────
USERNAME = "keelbismark"
ACCENT = "ff2e88"
ASSETS = Path(__file__).parent / "assets"
README = Path(__file__).parent / "README.md"
AUTO_START = "<!-- AUTO:START -->"
AUTO_END = "<!-- AUTO:END -->"
GRAPHQL_URL = "https://api.github.com/graphql"

# ── design system (shared by all generated svg) ──────────────────────
SHARED_CSS = """
  .sans { font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
  .mono { font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace; }
  .label { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 10px; fill: #6b5a68; letter-spacing: 2px; }
  .accent { fill: #ff2e88; }
  .white { fill: #f5f0f4; }
  .text { fill: #d4c8d1; }
  .muted { fill: #93838f; }
  .card-bg { fill: url(#cardGrad); }
  .edge { fill: none; stroke: url(#edgeGrad); }
  .rise { opacity: 0; animation: rise .7s cubic-bezier(.22,.9,.3,1.05) forwards; }
  .fadeup { opacity: 0; animation: fadeup .5s cubic-bezier(.22,.9,.3,1.05) forwards; }
  @keyframes rise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes fadeup { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  @media (prefers-reduced-motion: reduce) { .rise, .fadeup { animation: none; opacity: 1; } }
"""


def svg_shell(width: int, height: int, title: str, body: str) -> str:
    """Panel + card wrapper in the profile design system."""
    return f"""<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title}">
<title>{title}</title>
<defs>
<style>{SHARED_CSS}</style>
<linearGradient id="cardGrad" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#16111b"/><stop offset="1" stop-color="#0d0a11"/>
</linearGradient>
<linearGradient id="edgeGrad" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#ffffff" stop-opacity="0.14"/><stop offset="1" stop-color="#ffffff" stop-opacity="0.04"/>
</linearGradient>
<linearGradient id="barGrad" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#ff2e88"/><stop offset="1" stop-color="#ff7ab8"/>
</linearGradient>
<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
  <path d="M40 0H0V40" fill="none" stroke="#ffffff" stroke-opacity="0.02"/>
</pattern>
<radialGradient id="glowTL" cx="0.15" cy="0" r="0.8">
  <stop offset="0" stop-color="#ff2e88" stop-opacity="0.05"/><stop offset="1" stop-color="#ff2e88" stop-opacity="0"/>
</radialGradient>
<filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">
  <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000000" flood-opacity="0.5"/>
  <feDropShadow dx="0" dy="12" stdDeviation="24" flood-color="#000000" flood-opacity="0.35"/>
</filter>
</defs>
<rect x="0" y="0" width="{width}" height="{height}" rx="24" fill="#08060b"/>
<rect x="0" y="0" width="{width}" height="{height}" rx="24" fill="url(#grid)"/>
<rect x="0" y="0" width="{width}" height="{height}" rx="24" fill="url(#glowTL)"/>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="24" fill="none" stroke="#ffffff" stroke-opacity="0.06"/>
<g class="rise">
  <rect class="card-bg" x="20" y="20" width="{width - 40}" height="{height - 40}" rx="20" filter="url(#shadow)"/>
  <rect class="edge" x="20.5" y="20.5" width="{width - 41}" height="{height - 41}" rx="20"/>
{body}
</g>
</svg>
"""


# ── data ──────────────────────────────────────────────────────────────
def fetch_profile(gh: Github) -> dict:
    user = gh.get_user(USERNAME)
    repos = [r for r in user.get_repos() if not r.fork and not r.private]

    languages: dict[str, int] = defaultdict(int)
    for repo in repos:
        try:
            for lang, bytes_ in repo.get_languages().items():
                languages[lang] += int(bytes_)
        except Exception:
            continue

    top = sorted(languages.items(), key=lambda kv: kv[1], reverse=True)[:6]
    total_bytes = sum(languages.values()) or 1

    return {
        "repos": len(repos),
        "stars": sum(r.stargazers_count for r in repos),
        "forks": sum(r.forks_count for r in repos),
        "followers": user.followers,
        "since": user.created_at.year,
        "languages": [(name, round(bytes_ / total_bytes * 100, 1)) for name, bytes_ in top],
    }


def fetch_contributions(token: str | None, gh: Github) -> dict[str, int]:
    """date iso -> contribution count. GraphQL with token, public events otherwise."""
    if token:
        query = """
        query($login: String!) {
          user(login: $login) {
            contributionsCollection {
              contributionCalendar {
                weeks { contributionDays { date contributionCount } }
              }
            }
          }
        }
        """
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": {"login": USERNAME}},
            headers={"Authorization": f"bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        weeks = resp.json()["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        return {
            day["date"]: day["contributionCount"]
            for week in weeks
            for day in week["contributionDays"]
        }

    counts: dict[str, int] = defaultdict(int)
    for event in gh.get_user(USERNAME).get_events():  # public, ~last 90 days
        counts[event.created_at.date().isoformat()] += 1
    return dict(counts)


# ── builders ─────────────────────────────────────────────────────────
def build_stats(d: dict) -> str:
    tiles = [
        ("public repos", str(d["repos"])),
        ("stars", str(d["stars"])),
        ("forks", str(d["forks"])),
        ("followers", str(d["followers"])),
        ("on github", f"since {d['since']}"),
    ]
    parts = [f'  <text class="label" x="44" y="62"><tspan class="accent">//</tspan> stats</text>']
    for i, (label, value) in enumerate(tiles):
        cx = 128 + i * 164
        parts.append(f'  <text class="sans white" x="{cx}" y="98" font-size="22" font-weight="700" text-anchor="middle">{value}</text>')
        parts.append(f'  <text class="sans muted" x="{cx}" y="118" font-size="9" text-anchor="middle">{label}</text>')
        if i:
            parts.append(f'  <line x1="{cx - 82}" y1="66" x2="{cx - 82}" y2="118" stroke="#ffffff" stroke-opacity="0.06"/>')
    return svg_shell(900, 150, "GitHub stats", "\n".join(parts))


def build_languages(d: dict) -> str:
    parts = [f'  <text class="label" x="44" y="62"><tspan class="accent">//</tspan> languages — real repo data</text>']
    for i, (name, pct) in enumerate(d["languages"]):
        y = 88 + i * 26
        w = max(4, round(pct / 100 * 560))
        delay = 0.2 + i * 0.1
        parts.append(f'  <g class="fadeup" style="animation-delay:{delay:.1f}s">')
        parts.append(f'    <text class="sans text" x="44" y="{y + 9}" font-size="11">{name}</text>')
        parts.append(f'    <rect x="170" y="{y}" width="560" height="10" rx="5" fill="#ffffff" fill-opacity="0.05"/>')
        parts.append(f'    <rect x="170" y="{y}" width="{w}" height="10" rx="5" fill="url(#barGrad)"/>')
        parts.append(f'    <text class="mono muted" x="856" y="{y + 9}" font-size="10" text-anchor="end">{pct}%</text>')
        parts.append("  </g>")
    return svg_shell(900, 260, "Languages", "\n".join(parts))


def level(count: int) -> int:
    if count == 0: return 0
    if count < 4: return 1
    if count < 8: return 2
    if count < 12: return 3
    return 4


OPACITY = {0: 0.05, 1: 0.25, 2: 0.45, 3: 0.7, 4: 1.0}
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def build_heatmap(days: dict[str, int]) -> str:
    today = date.today()
    start = today - timedelta(days=364)
    start -= timedelta(days=(start.weekday() + 1) % 7)  # align to sunday

    total = sum(days.values())
    parts = [
        f'  <text class="label" x="44" y="62"><tspan class="accent">//</tspan> activity — {total} contributions / year</text>',
        '  <text class="sans muted" x="736" y="62" font-size="8">less</text>',
    ]
    for i in range(5):
        parts.append(f'  <rect x="{760 + i * 15}" y="53" width="12" height="12" rx="3" fill="#{"ffffff" if i == 0 else ACCENT}" fill-opacity="{OPACITY[i]}"/>')
    parts.append('  <text class="sans muted" x="856" y="62" font-size="8" text-anchor="end">more</text>')

    prev_month = -1
    for w in range(53):
        week_start = start + timedelta(weeks=w)
        if week_start.month != prev_month and week_start.day <= 7:
            parts.append(f'  <text class="mono muted" x="{44 + w * 15}" y="196" font-size="8">{MONTHS[week_start.month - 1]}</text>')
            prev_month = week_start.month
        for d in range(7):
            day = week_start + timedelta(days=d)
            if day > today:
                continue
            lv = level(days.get(day.isoformat(), 0))
            fill = "#ffffff" if lv == 0 else f"#{ACCENT}"
            parts.append(
                f'  <rect x="{44 + w * 15}" y="{72 + d * 15}" width="12" height="12" rx="3" fill="{fill}" fill-opacity="{OPACITY[lv]}"/>'
            )
    return svg_shell(900, 220, "Contribution heatmap", "\n".join(parts))


# ── readme ────────────────────────────────────────────────────────────
def update_readme() -> None:
    block = "\n".join(
        [
            AUTO_START,
            '<div align="center">',
            '  <img src="./assets/stats.svg" width="900" alt="GitHub stats"/>',
            "</div>",
            "",
            '<div align="center">',
            '  <img src="./assets/heatmap.svg" width="900" alt="Contribution heatmap"/>',
            "</div>",
            "",
            '<div align="center">',
            '  <img src="./assets/languages.svg" width="900" alt="Languages"/>',
            "</div>",
            f"<!-- regenerated: {date.today().isoformat()} -->",
            AUTO_END,
        ]
    )
    text = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END), re.S)
    if pattern.search(text):
        text = pattern.sub(block.replace("\\", "\\\\"), text, count=1)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    README.write_text(text, encoding="utf-8")


# ── main ──────────────────────────────────────────────────────────────
def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    gh = Github(auth=Auth.Token(token)) if token else Github()

    print(f"→ fetching profile data for {USERNAME}...")
    data = fetch_profile(gh)
    print(f"→ fetching contributions ({'graphql' if token else 'public events fallback'})...")
    days = fetch_contributions(token, gh)

    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "stats.svg").write_text(build_stats(data), encoding="utf-8")
    (ASSETS / "languages.svg").write_text(build_languages(data), encoding="utf-8")
    (ASSETS / "heatmap.svg").write_text(build_heatmap(days), encoding="utf-8")
    update_readme()

    print(f"✓ repos={data['repos']} stars={data['stars']} followers={data['followers']} days={len(days)}")
    print("✓ stats.svg / heatmap.svg / languages.svg / README.md refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())