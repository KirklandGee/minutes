"""Configuration loaded from $XDG_CONFIG_HOME/minutes/config.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


CONFIG_PATH = _xdg("XDG_CONFIG_HOME", ".config") / "minutes" / "config.toml"
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "minutes"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/minutes-{os.getuid()}") / "minutes"

DEFAULT_SUMMARY_PROMPT = """\
You are given a meeting transcript. "Me" is the person who recorded it; "Them" is everyone else on the call.

Respond with Markdown only, in exactly this shape:

Title: <a short descriptive title for the meeting, under 8 words>

### Overview
<2-4 sentence summary>

### Key points
- <bullets>

### Decisions
- <bullets, or "None">

### Action items
- [ ] <owner if known>: <task>
"""


@dataclass
class Config:
    # Where transcripts (.md) are written.
    output_dir: Path = Path.home() / "Meetings"
    # Where raw audio sessions live.
    audio_dir: Path = DATA_DIR / "sessions"
    # Keep the audio after transcription (lets you re-transcribe later).
    keep_audio: bool = True

    # faster-whisper model: tiny.en, base.en, small.en, medium.en, large-v3, distil-large-v3, ...
    model: str = "small.en"
    language: str | None = "en"
    compute_type: str = "int8"
    beam_size: int = 5

    # Run `claude -p` on the transcript to add a summary + title.
    summarize: bool = True
    claude_command: str = "claude"
    summary_prompt: str = DEFAULT_SUMMARY_PROMPT

    # iCal feeds (URLs or .ics paths) used to title meetings and list attendees.
    # For Google Calendar: Settings -> your calendar -> Integrate calendar -> "Secret address in iCal format".
    calendars: list[str] = field(default_factory=list)
    # Your calendar address, so overlapping events you declined are skipped.
    calendar_email: str | None = None
    # A recording may start up to this many minutes before its event.
    calendar_window: float = 15.0

    # Substrings matched against the binary/app name of anything holding the mic.
    apps: list[str] = field(
        default_factory=lambda: [
            "zoom", "chrome", "chromium", "firefox", "brave", "vivaldi", "edge",
            "slack", "teams", "discord", "webex", "signal",
        ]
    )
    # Seconds a meeting app must hold the mic before recording starts.
    start_delay: float = 3.0
    # Seconds after the mic is released before recording stops (apps blip on device changes).
    stop_delay: float = 20.0
    # Auto-recordings shorter than this many seconds are discarded.
    min_duration: float = 30.0
    poll_interval: float = 2.0

    notify: bool = True


def load(path: Path = CONFIG_PATH) -> Config:
    cfg = Config()
    if not path.exists():
        return cfg
    with path.open("rb") as f:
        data = tomllib.load(f)
    known = {f.name: f for f in fields(Config)}
    for key, value in data.items():
        if key not in known:
            raise SystemExit(f"minutes: unknown config key {key!r} in {path}")
        if key.endswith("_dir"):
            value = Path(value).expanduser()
        setattr(cfg, key, value)
    return cfg
