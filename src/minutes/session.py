"""A recording session: capture until signalled, then transcribe, write Markdown, summarize."""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from minutes import calendar, markdown
from minutes.config import RUNTIME_DIR, Config
from minutes.recorder import Recorder, duration
from minutes.summarize import summarize_file
from minutes.transcribe import transcribe

log = logging.getLogger("minutes")
STATE_PATH = RUNTIME_DIR / "recording.json"


def notify(cfg: Config, summary: str, body: str = "") -> None:
    if cfg.notify and shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "minutes", summary, body], check=False)


def current() -> dict | None:
    """The active recording's state, or None. Cleans up state left by a dead process."""
    try:
        state = json.loads(STATE_PATH.read_text())
        os.kill(state["pid"], 0)
        return state
    except FileNotFoundError:
        return None
    except (ProcessLookupError, json.JSONDecodeError, KeyError):
        STATE_PATH.unlink(missing_ok=True)
        return None


def record(
    cfg: Config,
    app: str = "manual",
    title: str | None = None,
    mic_source: str | None = None,
    auto: bool = False,
) -> Path | None:
    """Record until SIGINT/SIGTERM, then process. Returns the Markdown path (None if discarded)."""
    if active := current():
        raise SystemExit(f"minutes: already recording (pid {active['pid']})")

    started = datetime.now().astimezone()
    session_dir = cfg.audio_dir / f"{started:%Y-%m-%d-%H%M%S}-{markdown.slugify(app)}"
    recorder = Recorder(session_dir, mic_source)

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    recorder.start()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({
        "pid": os.getpid(), "app": app, "auto": auto,
        "started": started.isoformat(), "session_dir": str(session_dir),
    }))
    (session_dir / "session.json").write_text(json.dumps({
        "app": app, "title": title, "started": started.isoformat(),
    }))
    log.info("recording %s -> %s", app, session_dir)
    notify(cfg, "Recording started", f"{app} · run `minutes stop` to end")

    while not stop.wait(1):
        pass

    wavs = recorder.stop()
    STATE_PATH.unlink(missing_ok=True)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_DFL)

    length = max((duration(w) for w in wavs.values()), default=0.0)
    if auto and length < cfg.min_duration:
        log.info("discarding %.0fs recording (min_duration=%s)", length, cfg.min_duration)
        shutil.rmtree(session_dir, ignore_errors=True)
        return None
    notify(cfg, "Recording stopped", f"Transcribing {markdown.clock(length)} of audio…")
    return process(session_dir, cfg)


def process(session_dir: Path, cfg: Config) -> Path:
    """Transcribe a session directory and write its Markdown file."""
    meta = json.loads((session_dir / "session.json").read_text())
    started = datetime.fromisoformat(meta["started"])
    app = meta["app"]
    wavs = {t: session_dir / f"{t}.wav" for t in ("mic", "system")}
    wavs = {t: p for t, p in wavs.items() if p.exists()}
    length = max((duration(w) for w in wavs.values()), default=0.0)

    log.info("transcribing %s with %s", session_dir, cfg.model)
    segments = transcribe(wavs, cfg)

    title, title_source, attendees = meta.get("title"), "manual", []
    if not title and (event := calendar.find_event(cfg, started)):
        log.info("matched calendar event %r", event.title)
        title, title_source, attendees = event.title, "calendar", event.attendees
    if not title:
        title = "Meeting" if app == "manual" else f"{app.title()} meeting"
        title_source = "default"

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    md_path = markdown.output_path(cfg.output_dir, started, title)
    md_path.write_text(markdown.render(
        title, started, app, length, segments,
        session_dir if cfg.keep_audio else None,
        None if cfg.summarize and segments else "_Not summarized._",
        title_source=title_source,
        attendees=attendees,
    ))
    log.info("wrote %s", md_path)

    if cfg.summarize and segments:
        try:
            md_path = summarize_file(md_path, cfg)
            log.info("summarized %s", md_path)
        except Exception as e:  # transcript is already safe on disk; don't lose it over this
            log.warning("summary failed: %s", e)
            notify(cfg, "Summary failed", str(e)[:200])

    if not cfg.keep_audio:
        shutil.rmtree(session_dir, ignore_errors=True)
    notify(cfg, "Meeting notes ready", str(md_path))
    return md_path
