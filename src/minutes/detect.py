"""Detect meeting apps by watching who is capturing from a microphone (via pactl / PipeWire)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

OWN_CLIENT_NAME = "minutes"


@dataclass
class MicUser:
    app: str  # matched entry from config.apps
    source: str | None  # name of the source (mic) the app is capturing from


def _pactl_json(*args: str) -> list[dict]:
    out = subprocess.run(
        ["pactl", "-f", "json", "list", *args], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(out or "[]")


def match_app(props: dict[str, str], apps: list[str]) -> str | None:
    """Return the configured app name that a stream's properties match, if any."""
    if props.get("application.name") == OWN_CLIENT_NAME:
        return None
    haystack = " ".join(
        props.get(k, "")
        for k in ("application.process.binary", "application.name", "application.id", "node.name")
    ).lower()
    return next((app for app in apps if app.lower() in haystack), None)


def find_meeting(apps: list[str]) -> MicUser | None:
    """Return the first meeting app currently capturing from a real (non-monitor) mic."""
    try:
        outputs = _pactl_json("source-outputs")
        sources = {s["index"]: s["name"] for s in _pactl_json("sources", "short")}
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return None
    for out in outputs:
        source = sources.get(out.get("source"))
        # Screen-share audio capture reads from a sink monitor, not a mic.
        if source and source.endswith(".monitor"):
            continue
        app = match_app(out.get("properties", {}), apps)
        if app:
            return MicUser(app=app, source=source)
    return None
