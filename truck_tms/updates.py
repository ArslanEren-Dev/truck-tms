"""Checks GitHub for a newer release (GUI-free).

Only the public "latest release" page of the project is read; nothing about the user or their
data is sent. The check runs at most once a day and can be turned off in Settings.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import date

from . import PROJECT_URL, __version__

API_URL = "https://api.github.com/repos/ArslanEren-Dev/truck-tms/releases/latest"


def parse_version(text: str) -> tuple[int, ...]:
    """'v0.6.0' -> (0, 6, 0); anything after the numbers (-beta…) is ignored."""
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    return tuple(int(p) for p in match.group(1).split(".")) if match else ()


def is_newer(latest: str, current: str = __version__) -> bool:
    new, old = parse_version(latest), parse_version(current)
    if not new:
        return False
    width = max(len(new), len(old))
    return new + (0,) * (width - len(new)) > old + (0,) * (width - len(old))


@dataclass
class Release:
    version: str
    url: str          # release page
    download: str     # direct link to TruckTMS.exe, or the release page


def parse_release(data: dict) -> Release | None:
    tag = data.get("tag_name") or ""
    if not parse_version(tag) or data.get("draft") or data.get("prerelease"):
        return None
    url = data.get("html_url") or f"{PROJECT_URL}/releases/latest"
    download = next((a.get("browser_download_url") for a in data.get("assets") or []
                     if str(a.get("name", "")).lower().endswith(".exe")), None)
    return Release(tag.lstrip("v"), url, download or url)


def fetch_latest(timeout: float = 6.0) -> Release | None:
    """Ask GitHub for the latest release; None on any network problem."""
    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"TruckTMS/{__version__}",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (fixed https URL)
            return parse_release(json.loads(response.read().decode("utf-8")))
    except (OSError, ValueError):
        return None


def check_due(last_checked: str | None, today: date | None = None) -> bool:
    """True when the last automatic check was not today."""
    return (last_checked or "") != (today or date.today()).isoformat()
