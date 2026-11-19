#!/usr/bin/env python3
"""
update.py — self-updating GitHub profile generator.

Fetches live metrics from GitHub API and generates SVG telemetry assets
(stats / languages) adhering to the unified cyber-telemetry design system,
then updates the AUTO-section in README.md.

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

# Fix Windows console UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

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
  .sans { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', Helvetica, Arial, sans-serif; }
  .mono { font-family: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace; }
  .accent { fill: #ff2e88; }
  .white { fill: #f8fafc; }
  .text { fill: #cbd5e1; }
  .muted { fill: #64748b; }
  .faint { fill: #475569; }
  .card-bg { fill: url(#cardGrad); }
  .edge { fill: none; stroke: url(#edgeGrad); }
  .chip { fill: #ffffff; fill-opacity: 0.03; stroke: #ffffff; stroke-opacity: 0.08; }
  .rise { opacity: 0; animation: rise 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
  .fadeup { opacity: 0; animation: fadeup 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
  .pulse { animation: pulse 2s ease-in-out infinite; }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes fadeup { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
  @media (prefers-reduced-motion: reduce) { .rise, .fadeup { animation: none; opacity: 1; transform: none; } .pulse { animation: none; } }
"""


def svg_shell(width: int, height: int, title: str, label: str, body: str) -> str:
    """Panel with cyber-telemetry header, responsive viewBox, and deep obsidian styling."""
    w = width - 40
    return f"""<svg width="100%" height="auto" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title}" preserveAspectRatio="xMidYMid meet">
<title>{title}</title>
<defs>
<style>{SHARED_CSS}</style>
<linearGradient id="cardGrad" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0%" stop-color="#120e17"/>
  <stop offset="100%" stop-color="#09070d"/>
</linearGradient>
<linearGradient id="edgeGrad" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0%" stop-color="#ffffff" stop-opacity="0.14"/>
  <stop offset="100%" stop-color="#ffffff" stop-opacity="0.03"/>
</linearGradient>
<linearGradient id="headerGrad" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0%" stop-color="#ff2e88" stop-opacity="0.12"/>
  <stop offset="100%" stop-color="#ff2e88" stop-opacity="0.0"/>
</linearGradient>
<linearGradient id="barGrad" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0%" stop-color="#ff2e88"/>
  <stop offset="100%" stop-color="#ff007f"/>
</linearGradient>
<pattern id="dotGrid" width="30" height="30" patternUnits="userSpaceOnUse">
  <circle cx="2" cy="2" r="0.8" fill="#ffffff" fill-opacity="0.04"/>
</pattern>
<radialGradient id="ambientGlow" cx="0.1" cy="0.1" r="0.7">
  <stop offset="0%" stop-color="#ff2e88" stop-opacity="0.06"/>
  <stop offset="100%" stop-color="#ff2e88" stop-opacity="0"/>
</radialGradient>
<filter id="shadowDepth" x="-20%" y="-20%" width="140%" height="140%">
  <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#000000" flood-opacity="0.6"/>
  <feDropShadow dx="0" dy="16" stdDeviation="20" flood-color="#000000" flood-opacity="0.4"/>
</filter>
<filter id="accentGlow" x="-30%" y="-30%" width="160%" height="160%">
  <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#ff2e88" flood-opacity="0.55"/>
</filter>
</defs>
<rect x="0" y="0" width="{width}" height="{height}" rx="20" fill="#07050a"/>
<rect x="0" y="0" width="{width}" height="{height}" rx="20" fill="url(#dotGrid)"/>
<rect x="0" y="0" width="{width}" height="{height}" rx="20" fill="url(#ambientGlow)"/>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="19.5" fill="none" stroke="#ffffff" stroke-opacity="0.06"/>
<g class="rise">
  <rect class="card-bg" x="20" y="16" width="{w}" height="{height - 32}" rx="16" filter="url(#shadowDepth)"/>
  <rect class="edge" x="20.5" y="16.5" width="{w - 1}" height="{height - 33}" rx="15.5"/>
  <rect x="21" y="17" width="{w - 2}" height="32" rx="15" fill="url(#headerGrad)"/>
  <text class="mono faint" x="38" y="38" font-size="10" font-weight="600" letter-spacing="1"><tspan class="accent">//</tspan> {label}</text>
  <circle cx="{width - 38}" cy="33" r="3" fill="#10b981" class="pulse"/>
  <text class="mono faint" x="{width - 48}" y="36" font-size="9" text-anchor="end">LIVE TELEMETRY</text>
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
        "languages": [(name, round(b / total_bytes * 100, 1)) for name, b in top],
    }


# ── builders ──────────────────────────────────────────────────────────
def build_stats(d: dict) -> str:
    tiles = [
        ("PUBLIC REPOS", str(d["repos"])),
        ("STARS EARNED", str(d["stars"])),
        ("FORKS REPLICATED", str(d["forks"])),
        ("GITHUB FOLLOWERS", str(d["followers"])),
        ("ACTIVE SINCE", str(d["since"])),
    ]
    parts = []
    for i, (label, value) in enumerate(tiles):
        cx = 126 + i * 164
        parts.append(
            f'  <text class="sans white" x="{cx}" y="88" font-size="24" font-weight="800" text-anchor="middle">{value}</text>'
        )
        parts.append(
            f'  <text class="mono faint" x="{cx}" y="108" font-size="9" font-weight="700" letter-spacing="0.5" text-anchor="middle">{label}</text>'
        )
        if i:
            parts.append(
                f'  <line x1="{cx - 82}.5" y1="62" x2="{cx - 82}.5" y2="114" stroke="#ffffff" stroke-opacity="0.05"/>'
            )
    return svg_shell(900, 146, "GitHub stats", "GITHUB.STATISTICS [CORE_METRICS]", "\n".join(parts))


def build_languages(d: dict) -> str:
    parts = []
    for i, (name, pct) in enumerate(d["languages"]):
        y = 74 + i * 26
        w = max(4, round(pct / 100 * 560))
        delay = 0.15 + i * 0.08
        parts.append(f'  <g class="fadeup" style="animation-delay:{delay:.2f}s">')
        parts.append(f'    <text class="mono text" x="42" y="{y + 9}" font-size="11" font-weight="500">{name}</text>')
        parts.append(
            f'    <rect x="170" y="{y}" width="560" height="10" rx="5" fill="#ffffff" fill-opacity="0.04"/>'
        )
        parts.append(f'    <rect x="170" y="{y}" width="{w}" height="10" rx="5" fill="url(#barGrad)"/>')
        parts.append(
            f'    <text class="mono faint" x="858" y="{y + 9}" font-size="10" font-weight="700" text-anchor="end">{pct}%</text>'
        )
        parts.append("  </g>")
    return svg_shell(
        900, 256, "Language Metrics", "REPO.ANALYTICS [DISTRIBUTION_PERCENTILE]", "\n".join(parts)
    )


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

    print(f"-> fetching profile data for {USERNAME}...")
    data = fetch_profile(gh)

    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "stats.svg").write_text(build_stats(data), encoding="utf-8")
    (ASSETS / "languages.svg").write_text(build_languages(data), encoding="utf-8")
    update_readme()

    print(f"[OK] repos={data['repos']} stars={data['stars']} followers={data['followers']}")
    print("[OK] stats.svg / languages.svg / README.md refreshed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())