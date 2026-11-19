#!/usr/bin/env python3
"""
update.py — self-updating GitHub profile generator.

Тянет реальные данные из GitHub API и перегенерирует SVG-ассеты
(stats / languages) в единой дизайн-системе профиля, затем обновляет
AUTO-секцию README.md. Все карточки — «окна» с одинаковой шапкой.

Heatmap не генерируется: нативный граф контрибуций уже есть на профиле.

Usage:
    python update.py                      # anonymous (60 req/h)
    GITHUB_TOKEN=... python update.py     # authenticated (5000 req/h)
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from github import Auth, Github

# ── config ────────────────────────────────────────────────────────────
USERNAME = "keelbismark"
ACCENT = "ff2e88"
ASSETS = Path(__file__).parent / "assets"
README = Path(__file__).parent / "README.md"
AUTO_START = "<!-- AUTO:START -->"
AUTO_END = "<!-- AUTO:END -->"

# ── design system (shared by all generated svg) ──────────────────────
SHARED_CSS = """
  .sans { font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
  .mono { font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace; }
  .accent { fill: #ff2e88; }
  .white { fill: #f5f0f4; }
  .text { fill: #d4c8d1; }
  .muted { fill: #93838f; }
  .card-bg { fill: url(#cardGrad); }
  .edge { fill: none; stroke: url(#edgeGrad); }
  .chip { fill: #ffffff; fill-opacity: 0.04; stroke: #ffffff; stroke-opacity: 0.10; }
  .rise { opacity: 0; animation: rise .7s cubic-bezier(.22,.9,.3,1.05) forwards; }
  .fadeup { opacity: 0; animation: fadeup .5s cubic-bezier(.22,.9,.3,1.05) forwards; }
  @keyframes rise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes fadeup { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  @media (prefers-reduced-motion: reduce) { .rise, .fadeup { animation: none; opacity: 1; } }
"""


def svg_shell(width: int, height: int, title: str, label: str, body: str) -> str:
    """Panel + window-card with the unified 30px header (dots + // label)."""
    w = width - 40
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
<linearGradient id="headGrad" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#1c1522"/><stop offset="1" stop-color="#141018"/>
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
  <rect class="card-bg" x="20" y="20" width="{w}" height="{height - 40}" rx="20" filter="url(#shadow)"/>
  <rect class="edge" x="20.5" y="20.5" width="{w - 1}" height="{height - 41}" rx="20"/>
  <path d="M20 40 a20 20 0 0 1 20 -20 h{w - 40} a20 20 0 0 1 20 20 v10 h-{w} z" fill="url(#headGrad)"/>
  <circle fill="#ff5f56" cx="40" cy="35" r="4"/>
  <circle fill="#ffbd2e" cx="56" cy="35" r="4"/>
  <circle fill="#27c93f" cx="72" cy="35" r="4"/>
  <text class="mono muted" x="{width // 2}" y="39" font-size="10" text-anchor="middle"><tspan class="accent">//</tspan> {label}</text>
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
            continue  # пустой репо или сбой API — пропускаем

    top = sorted(languages.items(), key=lambda kv: kv[1], reverse=True)[:6]
    total_bytes = sum(languages.values()) or 1

    return {
        "repos": len(repos),
        "stars": sum(r.stargazers_count for r in repos),
        "forks": sum(r.forks_count for r in repos),
        "followers": user.followers,
        "since": user.created_at.year,
        "languages": [(name, round(b / total_bytes * 100, 1)) for name, b in top],
    }


# ── builders ──────────────────────────────────────────────────────────
def build_stats(d: dict) -> str:
    tiles = [
        ("public repos", str(d["repos"])),
        ("stars", str(d["stars"])),
        ("forks", str(d["forks"])),
        ("followers", str(d["followers"])),
        ("on github", f"since {d['since']}"),
    ]
    parts = []
    for i, (label, value) in enumerate(tiles):
        cx = 128 + i * 164
        parts.append(f'  <text class="sans white" x="{cx}" y="92" font-size="22" font-weight="700" text-anchor="middle">{value}</text>')
        parts.append(f'  <text class="sans muted" x="{cx}" y="112" font-size="9" text-anchor="middle">{label}</text>')
        if i:
            parts.append(f'  <line x1="{cx - 82}" y1="64" x2="{cx - 82}" y2="112" stroke="#ffffff" stroke-opacity="0.06"/>')
    return svg_shell(900, 150, "GitHub stats", "stats", "\n".join(parts))


def build_languages(d: dict) -> str:
    parts = []
    for i, (name, pct) in enumerate(d["languages"]):
        y = 78 + i * 26
        w = max(4, round(pct / 100 * 560))
        delay = 0.2 + i * 0.1
        parts.append(f'  <g class="fadeup" style="animation-delay:{delay:.1f}s">')
        parts.append(f'    <text class="sans text" x="44" y="{y + 9}" font-size="11">{name}</text>')
        parts.append(f'    <rect x="170" y="{y}" width="560" height="10" rx="5" fill="#ffffff" fill-opacity="0.05"/>')
        parts.append(f'    <rect x="170" y="{y}" width="{w}" height="10" rx="5" fill="url(#barGrad)"/>')
        parts.append(f'    <text class="mono muted" x="856" y="{y + 9}" font-size="10" text-anchor="end">{pct}%</text>')
        parts.append("  </g>")
    return svg_shell(900, 260, "Languages", "languages — real repo data", "\n".join(parts))


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
            '  <img src="./assets/languages.svg" width="900" alt="Languages"/>',
            "</div>",
            f"<!-- regenerated: {date.today().isoformat()} -->",
            AUTO_END,
        ]
    )
    text = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(AUTO_START) + r".*?" + re.escape(AUTO_END), re.S)
    if pattern.search(text):
        text = pattern.sub(lambda m: block, text, count=1)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    README.write_text(text, encoding="utf-8")


# ── main ──────────────────────────────────────────────────────────────
def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    gh = Github(auth=Auth.Token(token)) if token else Github()

    print(f"→ fetching profile data for {USERNAME}...")
    data = fetch_profile(gh)

    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "stats.svg").write_text(build_stats(data), encoding="utf-8")
    (ASSETS / "languages.svg").write_text(build_languages(data), encoding="utf-8")
    update_readme()

    print(f"✓ repos={data['repos']} stars={data['stars']} followers={data['followers']}")
    print("✓ stats.svg / languages.svg / README.md refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())