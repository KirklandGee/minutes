"""Detect meeting apps by watching who is capturing from a microphone (via pactl / PipeWire)."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from minutes.config import BROWSERS, Config

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


def windows() -> list[tuple[str, str]] | None:
    """Lowercased (class, title) of every open Hyprland window, or None outside Hyprland."""
    try:
        out = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, check=True).stdout
        return [(c.get("class", "").lower(), c.get("title", "").lower()) for c in json.loads(out)]
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return None


def ignored_browser_use(cfg: Config, wins: list[tuple[str, str]] | None) -> bool:
    """A browser holds the mic, but an ignored web app (e.g. Discord) is open and no window looks like a call.

    The browser's audio stream doesn't say which tab or web app is using the mic, so we go by open windows.
    Ignored apps match the window class only, so a tab or terminal that merely mentions "discord" doesn't count.
    """
    if not wins:
        return False
    ignored = any(p.lower() in cls for cls, _ in wins for p in cfg.ignore_windows)
    call = any(p.lower() in f"{cls} {title}" for cls, title in wins for p in cfg.meeting_windows)
    return ignored and not call


def find_meeting(cfg: Config) -> MicUser | None:
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
        app = match_app(out.get("properties", {}), cfg.apps)
        if app and app in BROWSERS and ignored_browser_use(cfg, windows()):
            continue
        if app:
            return MicUser(app=app, source=source)
    return None
