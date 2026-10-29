"""Render and update meeting Markdown files."""

from __future__ import annotations

import json
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
    title_source: str = "default",
    attendees: list[str] | None = None,
) -> str:
    # JSON strings/lists are valid YAML, and survive titles like "Sync: Q4".
    front = [
        "---",
        f"title: {json.dumps(title)}",
        f"title_source: {title_source}",
        f"date: {started.isoformat(timespec='seconds')}",
        f"app: {app}",
        f"duration: {clock(duration)}",
    ]
    if attendees:
        front.append(f"attendees: {json.dumps(attendees)}")
    if audio_dir:
        front.append(f"audio: {json.dumps(str(audio_dir))}")
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
        md = re.sub(r"^title: .*$", lambda _: f"title: {json.dumps(title)}", md, count=1, flags=re.M)
        md = re.sub(r"^title_source: .*$", "title_source: claude", md, count=1, flags=re.M)
        md = re.sub(r"^# .*$", lambda _: f"# {title}", md, count=1, flags=re.M)
    return md


def frontmatter(md: str) -> str:
    match = re.match(r"---\n.*?\n---\n", md, flags=re.S)
    return match.group(0) if match else ""


def field(md: str, key: str) -> str | None:
    """A scalar frontmatter value (unquoted), or None."""
    match = re.search(rf"^{re.escape(key)}: (.*)$", frontmatter(md), flags=re.M)
    if not match:
        return None
    value = match.group(1).strip()
    return json.loads(value) if value.startswith('"') else value


def transcript_text(md: str) -> str:
    _, _, transcript = md.partition("## Transcript")
    return transcript.strip()
