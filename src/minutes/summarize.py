"""Summarize a transcript with Claude Code (`claude -p`), using your existing subscription."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from minutes import markdown
from minutes.config import Config


def summarize_file(md_path: Path, cfg: Config) -> Path:
    """Fill in the Summary section of a meeting file. Renames it if Claude suggests a title.

    Returns the (possibly new) path.
    """
    claude = shutil.which(cfg.claude_command)
    if not claude:
        raise RuntimeError(f"{cfg.claude_command!r} not found on PATH")
    md = md_path.read_text()
    transcript = markdown.transcript_text(md)
    result = subprocess.run(
        [claude, "-p", cfg.summary_prompt, "--output-format", "text"],
        input=transcript,
        capture_output=True,
        text=True,
        cwd=md_path.parent,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude exited {result.returncode}: {result.stderr.strip()[:500]}")
    title, summary = split_title(result.stdout)
    md_path.write_text(markdown.set_summary(md, summary, title))
    if title:
        # Keep the timestamp prefix, swap the slug.
        new_path = md_path.with_name(f"{md_path.name[:15]}-{markdown.slugify(title)}.md")
        if new_path != md_path and not new_path.exists():
            md_path = md_path.rename(new_path)
    return md_path


def split_title(output: str) -> tuple[str | None, str]:
    match = re.match(r"\s*Title:\s*(.+?)\s*\n", output)
    if not match:
        return None, output.strip()
    return match.group(1).strip("*# "), output[match.end():].strip()
