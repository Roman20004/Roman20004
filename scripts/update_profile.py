from __future__ import annotations

import base64
import calendar
import datetime as dt
import html
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
PORTRAIT_DATA = base64.b64encode(
    (ROOT / "assets" / "terminal-green-concept.png").read_bytes()
).decode("ascii")
TOKEN = os.getenv("PROFILE_TOKEN") or os.getenv("GITHUB_TOKEN")


THEMES = {
    "dark_mode.svg": {
        "background": "#080d08",
        "panel": "#0b120b",
        "border": "#66b83e",
        "portrait": "#75d14a",
        "key": "#8ee45d",
        "value": "#efe4c2",
        "muted": "#416f31",
        "accent": "#f0ad32",
        "scanline": "#b8ff9a",
    },
    "light_mode.svg": {
        "background": "#080d08",
        "panel": "#0b120b",
        "border": "#66b83e",
        "portrait": "#75d14a",
        "key": "#8ee45d",
        "value": "#efe4c2",
        "muted": "#416f31",
        "accent": "#f0ad32",
        "scanline": "#b8ff9a",
    },
}


def request_json(url: str, payload: dict[str, Any] | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Roman20004-profile-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = json.dumps(payload).encode("utf-8") if payload else None
    request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def public_repositories(username: str) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = request_json(
            f"https://api.github.com/users/{username}/repos"
            f"?type=owner&sort=updated&per_page=100&page={page}"
        )
        repositories.extend(repo for repo in batch if not repo.get("fork"))
        if len(batch) < 100:
            return repositories
        page += 1


def public_contributions(username: str, now: dt.datetime) -> int | None:
    if not TOKEN:
        return None
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar { totalContributions }
          restrictedContributionsCount
        }
      }
    }
    """
    result = request_json(
        "https://api.github.com/graphql",
        {
            "query": query,
            "variables": {
                "login": username,
                "from": f"{now.year}-01-01T00:00:00Z",
                "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        },
    )
    collection = result["data"]["user"]["contributionsCollection"]
    total = collection["contributionCalendar"]["totalContributions"]
    return max(0, total - collection["restrictedContributionsCount"])


def add_months(value: dt.datetime, months: int) -> dt.datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def elapsed(start: dt.datetime, end: dt.datetime) -> str:
    months = max(0, (end.year - start.year) * 12 + end.month - start.month)
    marker = add_months(start, months)
    if marker > end:
        months -= 1
        marker = add_months(start, months)
    days = (end - marker).days
    years, remaining_months = divmod(months, 12)
    parts: list[str] = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if remaining_months:
        parts.append(f"{remaining_months} month{'s' if remaining_months != 1 else ''}")
    parts.append(f"{days} day{'s' if days != 1 else ''}")
    return ", ".join(parts)


def collect_stats() -> dict[str, Any]:
    username = PROFILE["username"]
    now = dt.datetime.now(dt.timezone.utc)
    created = dt.datetime.fromisoformat(PROFILE["account_created"].replace("Z", "+00:00"))
    stats: dict[str, Any] = {
        "account_uptime": elapsed(created, now),
        "last_refresh": now.strftime("%d %b %Y"),
        "public_repos": 0,
        "stars": 0,
        "followers": 0,
        "contributions": None,
    }
    try:
        user = request_json(f"https://api.github.com/users/{username}")
        repositories = public_repositories(username)
        stats.update(
            public_repos=len(repositories),
            stars=sum(repo.get("stargazers_count", 0) for repo in repositories),
            followers=user.get("followers", 0),
            contributions=public_contributions(username, now),
        )
    except (HTTPError, URLError, TimeoutError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"GitHub data unavailable; rendering stable profile fields: {error}")
    return stats


def xml(value: Any) -> str:
    return html.escape(str(value), quote=True)


def row(
    label: str,
    value: str,
    y: int,
    *,
    accent: bool = False,
    value_x: int = 1050,
) -> str:
    value_class = "accent" if accent else "value"
    return (
        f'<text y="{y}" class="row">'
        f'<tspan x="710" class="key">{xml(label)}</tspan>'
        f'<tspan x="835" class="dots">................</tspan>'
        f'<tspan x="{value_x}" class="{value_class}">{xml(value)}</tspan>'
        "</text>"
    )


def build_svg(theme: dict[str, str], stats: dict[str, Any]) -> str:
    info_rows = [
        ("Role:", PROFILE["role"]),
        ("OS:", PROFILE["os"]),
        ("Host:", PROFILE["host"]),
        ("IDE:", PROFILE["ide"]),
        ("Stack:", PROFILE["stack"]),
        ("Interests:", PROFILE["interests"]),
    ]
    info = [row(label, value, 218 + index * 68) for index, (label, value) in enumerate(info_rows)]

    activity: list[tuple[str, str]] = [("Account Uptime:", stats["account_uptime"])]
    optional = [
        ("Public Repos:", stats["public_repos"]),
        ("Contributions:", stats["contributions"]),
        ("Stars:", stats["stars"]),
        ("Followers:", stats["followers"]),
    ]
    activity.extend((label, f"{value:,}") for label, value in optional if value)
    activity.append(("Last Refresh:", stats["last_refresh"]))
    activity = activity[:4]
    activity_rows = [
        row(label, value, 725 + index * 50, accent=True, value_x=1320)
        for index, (label, value) in enumerate(activity)
    ]

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1680" height="940" viewBox="0 0 1680 940" role="img" aria-labelledby="title desc">
  <title id="title">{xml(PROFILE['display_name'])} GitHub profile</title>
  <desc id="desc">Terminal-style profile card with an ASCII portrait and automatically refreshed public GitHub activity.</desc>
  <defs>
    <pattern id="scanlines" width="4" height="4" patternUnits="userSpaceOnUse">
      <path d="M0 3.5H4" stroke="{theme['scanline']}" stroke-opacity="0.025" stroke-width="1"/>
    </pattern>
    <filter id="soft-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="2.2" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <style>
    .mono {{ font-family: Consolas, 'Cascadia Mono', 'Courier New', monospace; }}
    .row {{ font: 22px Consolas, 'Cascadia Mono', 'Courier New', monospace; white-space: pre; }}
    .key {{ fill: {theme['key']}; font-weight: 700; }}
    .value {{ fill: {theme['value']}; }}
    .dots {{ fill: {theme['muted']}; }}
    .accent {{ fill: {theme['accent']}; font-weight: 700; }}
  </style>
  <rect width="1680" height="940" fill="{theme['background']}"/>
  <rect x="20" y="22" width="1640" height="896" rx="34" fill="{theme['panel']}" stroke="{theme['border']}" stroke-width="2"/>
  <image href="data:image/png;base64,{PORTRAIT_DATA}" x="0" y="0" width="1680" height="940" preserveAspectRatio="none"/>
  <rect x="670" y="23" width="989" height="894" fill="{theme['panel']}"/>
  <path d="M670 42V898" stroke="{theme['border']}" stroke-width="1" opacity="0.28"/>
  <rect x="20" y="22" width="1640" height="896" rx="34" fill="url(#scanlines)"/>
  <text x="710" y="120" class="mono" fill="{theme['key']}" font-size="48" font-weight="700" filter="url(#soft-glow)">{xml(PROFILE['terminal_name'])}</text>
  <path d="M710 158H1595" stroke="{theme['border']}" stroke-width="2" opacity="0.8"/>
  {''.join(info)}
  <path d="M710 642H1595" stroke="{theme['border']}" stroke-width="2" opacity="0.8"/>
  <text x="710" y="680" class="mono" fill="{theme['accent']}" font-size="30" font-weight="700">GitHub Activity</text>
  {''.join(activity_rows)}
  <path d="M710 900H1595" stroke="{theme['border']}" stroke-width="2" opacity="0.55"/>
  <rect x="20" y="22" width="1640" height="896" rx="34" fill="none" stroke="{theme['border']}" stroke-width="2"/>
</svg>
'''


def main() -> None:
    stats = collect_stats()
    for filename, theme in THEMES.items():
        (ROOT / filename).write_text(build_svg(theme, stats), encoding="utf-8", newline="\n")
        print(f"Updated {filename}")


if __name__ == "__main__":
    main()
