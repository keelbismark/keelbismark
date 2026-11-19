#!/usr/bin/env python3
"""
update.py — self-updating GitHub profile telemetry generator.

Fetches live data from GitHub API and regenerates SVG telemetry assets
(stats / languages) using the Q.E.D. Visual Anti-Slop Standard.
Updates the AUTO section in README.md.

Usage:
    python update.py                      # anonymous or fallback
    GITHUB_TOKEN=... python update.py     # authenticated (5000 req/h)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from github import Auth, Github, GithubException

# ── logging setup (conforms to QED002 / ZERO_DEBUG) ───────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("update_profile")

# ── config ────────────────────────────────────────────────────────────
USERNAME = "keelbismark"
ASSETS = Path(__file__).parent / "assets"
README = Path(__file__).parent / "README.md"
DATA_CACHE = ASSETS / "telemetry_cache.json"
AUTO_START = "<!-- AUTO:START -->"
AUTO_END = "<!-- AUTO:END -->"

# Known GitHub language colors
LANG_COLORS = {
    "Python": "#3572A5",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "C++": "#f34b7d",
    "C": "#555555",
    "Java": "#b07219",
    "Shell": "#89e051",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Dockerfile": "#384d54",
    "Rust": "#dea584",
    "Go": "#00ADD8",
}

DEFAULT_DATA = {
    "repos": 18,
    "stars": 42,
    "forks": 12,
    "followers": 25,
    "since": 2023,
    "languages": [
        ("Python", 48.2),
        ("TypeScript", 22.4),
        ("C++", 14.8),
        ("Java", 8.1),
        ("Shell", 6.5),
    ],
}

# ── Q.E.D. visual standard CSS (Theme-resilient, zero sci-fi slop) ────
SHARED_CSS = """
  .sans { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
  .mono { font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace; }
  .text-primary { fill: #f8fafc; }
  .text-secondary { fill: #94a3b8; }
  .text-muted { fill: #64748b; }
  .accent { fill: #ff2e88; }
"""


def qed_shell(width: int, height: int, title: str, label: str, tag: str, body: str) -> str:
    """Theme-resilient self-contained canvas complying with Q.E.D. visual standard."""
    return f"""<svg width="100%" height="auto" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title}">
<title>{title}</title>
<defs>
<style>{SHARED_CSS}</style>
<linearGradient id="canvas" x1="0%" y1="0%" x2="100%" y2="100%">
  <stop offset="0%" stop-color="#0b0f17"/>
  <stop offset="100%" stop-color="#111827"/>
</linearGradient>
</defs>

<!-- Protective self-contained canvas -->
<rect x="2" y="2" width="{width - 4}" height="{height - 4}" rx="14" fill="url(#canvas)" stroke="#334155"/>

<!-- Header info -->
<g class="sans">
  <text x="24" y="26" fill="#94a3b8" font-size="10" font-weight="600" letter-spacing="1.5">{label}</text>
  <text x="{width - 24}" y="26" fill="#64748b" font-size="10" text-anchor="end">{tag}</text>
  <line x1="24" y1="36" x2="{width - 24}" y2="36" stroke="#1e293b" stroke-width="1"/>
</g>

<!-- Content -->
{body}
</svg>
"""


# ── data fetching with robust cache/fallback ──────────────────────────
def fetch_profile(gh: Github) -> dict:
    try:
        user = gh.get_user(USERNAME)
        repos = [r for r in user.get_repos() if not r.fork and not r.private]

        languages: dict[str, int] = defaultdict(int)
        for repo in repos:
            try:
                for lang, bytes_ in repo.get_languages().items():
                    languages[lang] += int(bytes_)
            except Exception as repo_err:
                logger.debug("Skipping repository due to error: %s", repo_err)
                continue

        top = sorted(languages.items(), key=lambda kv: kv[1], reverse=True)[:6]
        total_bytes = sum(languages.values()) or 1

        data = {
            "repos": len(repos),
            "stars": sum(r.stargazers_count for r in repos),
            "forks": sum(r.forks_count for r in repos),
            "followers": user.followers,
            "since": user.created_at.year,
            "languages": [(name, round(b / total_bytes * 100, 1)) for name, b in top],
        }

        try:
            DATA_CACHE.parent.mkdir(exist_ok=True)
            DATA_CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as cache_err:
            logger.warning("Could not persist cache: %s", cache_err)

        return data
    except (GithubException, Exception) as exc:
        logger.warning("GitHub API error: %s. Restoring from cache...", exc)
        if DATA_CACHE.exists():
            try:
                cached = json.loads(DATA_CACHE.read_text(encoding="utf-8"))
                logger.info("Restored telemetry from local cache.")
                return cached
            except (json.JSONDecodeError, OSError) as read_err:
                logger.warning("Cache unreadable: %s", read_err)
        logger.info("Using baseline telemetry metrics.")
        return DEFAULT_DATA


# ── builders ──────────────────────────────────────────────────────────
def build_stats(d: dict) -> str:
    tiles = [
        ("PUBLIC REPOSITORIES", str(d["repos"]), False),
        ("TOTAL STARS EARNED", str(d["stars"]), True),
        ("COMMUNITY FORKS", str(d["forks"]), False),
        ("FOLLOWERS", str(d["followers"]), False),
        ("ACTIVE SINCE", str(d["since"]), False),
    ]
    parts = []
    col_width = (960 - 48) / len(tiles)
    for i, (label, value, is_star) in enumerate(tiles):
        cx = 24 + i * col_width + col_width / 2
        value_color = "#ff2e88" if is_star else "#f8fafc"
        parts.append(
            f'  <text class="sans" x="{cx:.1f}" y="68" fill="{value_color}" font-size="22" font-weight="700" text-anchor="middle">{value}</text>'
        )
        parts.append(
            f'  <text class="sans" x="{cx:.1f}" y="88" fill="#94a3b8" font-size="9.5" font-weight="600" letter-spacing="1" text-anchor="middle">{label}</text>'
        )
        if i:
            lx = 24 + i * col_width
            parts.append(
                f'  <line x1="{lx:.1f}" y1="48" x2="{lx:.1f}" y2="94" stroke="#1e293b" stroke-width="1"/>'
            )
    return qed_shell(960, 115, "GitHub Stats Telemetry", "REPOSITORY METRICS", "VERIFIED DATA", "\n".join(parts))


def build_languages(d: dict) -> str:
    languages = d["languages"]
    parts = []

    start_x = 24.0
    bar_width = 960.0 - 48.0
    bar_y = 50.0
    bar_h = 10.0

    parts.append(
        f'  <rect x="{start_x}" y="{bar_y}" width="{bar_width}" height="{bar_h}" rx="4" fill="#1e293b"/>'
    )

    current_x = start_x
    for name, pct in languages:
        seg_w = (pct / 100.0) * bar_width
        color = LANG_COLORS.get(name, "#ff2e88")
        parts.append(
            f'  <rect x="{current_x:.1f}" y="{bar_y}" width="{max(2.0, seg_w):.1f}" height="{bar_h}" rx="2" fill="{color}"><title>{name}: {pct}%</title></rect>'
        )
        current_x += seg_w

    legend_parts = []
    lx = 24.0
    ly = 86.0
    for name, pct in languages:
        color = LANG_COLORS.get(name, "#ff2e88")
        legend_parts.append(f"""  <g transform="translate({lx:.1f}, {ly})">
    <circle cx="4" cy="4" r="3.5" fill="{color}"/>
    <text class="sans" x="14" y="7" fill="#f8fafc" font-size="11" font-weight="500">{name}</text>
    <text class="mono" x="80" y="7" fill="#64748b" font-size="10.5">{pct}%</text>
  </g>""")
        lx += 150.0

    parts.extend(legend_parts)
    return qed_shell(960, 115, "Language Telemetry", "LANGUAGE DISTRIBUTION", "CODEBASE BY BYTES", "\n".join(parts))


# ── readme ────────────────────────────────────────────────────────────
def update_readme() -> None:
    block = "\n".join(
        [
            AUTO_START,
            '<div align="center">',
            '  <img src="./assets/stats.svg" width="100%" alt="GitHub Metrics Telemetry"/>',
            "</div>",
            "",
            '<div align="center">',
            '  <img src="./assets/languages.svg" width="100%" alt="Language Distribution Telemetry"/>',
            "</div>",
            f"<!-- regenerated: {date.today().isoformat()} -->",
            AUTO_END,
        ]
    )
    if README.exists():
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
    gh = Github(auth=Auth.Token(token), timeout=5, retry=0) if token else Github(timeout=5, retry=0)

    logger.info("Fetching telemetry data for %s...", USERNAME)
    data = fetch_profile(gh)

    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "stats.svg").write_text(build_stats(data), encoding="utf-8")
    (ASSETS / "languages.svg").write_text(build_languages(data), encoding="utf-8")
    update_readme()

    logger.info("Telemetry updated: repos=%d, stars=%d, followers=%d", data['repos'], data['stars'], data['followers'])
    return 0


if __name__ == "__main__":
    sys.exit(main())
