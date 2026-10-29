"""Render and update meeting Markdown files."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from minutes.transcribe import Segment

SUMMARY_PLACEHOLDER = "_Summary pending._"


def clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "meeting"


def render(
    title: str,
    started: datetime,
    app: str,
    duration: float,
    segments: list[Segment],
    audio_dir: Path | None,
    summary: str | None,
) -> str:
    front = [
        "---",
        f"title: {title}",
        f"date: {started.isoformat(timespec='seconds')}",
        f"app: {app}",
        f"duration: {clock(duration)}",
    ]
    if audio_dir:
        front.append(f"audio: {audio_dir}")
    front.append("---")
    body = [
        "",
        f"# {title}",
        "",
        f"{started:%A, %B %-d, %Y at %-I:%M %p} · {app} · {clock(duration)}",
        "",
        "## Summary",
        "",
        summary or SUMMARY_PLACEHOLDER,
        "",
        "## Transcript",
        "",
    ]
    lines = [f"**[{clock(s.start)}] {s.speaker}:** {s.text}\n" for s in segments]
    if not lines:
        lines = ["_No speech detected._\n"]
    return "\n".join(front + body) + "\n" + "\n".join(lines)


def output_path(output_dir: Path, started: datetime, title: str) -> Path:
    return output_dir / f"{started:%Y-%m-%d-%H%M}-{slugify(title)}.md"


def set_summary(md: str, summary: str, title: str | None) -> str:
    """Replace the Summary section body (and the title, if given)."""
    md = re.sub(
        r"(## Summary\n\n).*?(\n## Transcript)",
        lambda m: f"{m.group(1)}{summary.strip()}\n{m.group(2)}",
        md,
        count=1,
        flags=re.S,
    )
    if title:
        md = re.sub(r"^title: .*$", f"title: {title}", md, count=1, flags=re.M)
        md = re.sub(r"^# .*$", f"# {title}", md, count=1, flags=re.M)
    return md


def transcript_text(md: str) -> str:
    _, _, transcript = md.partition("## Transcript")
    return transcript.strip()
