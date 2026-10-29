"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from minutes import __version__, config, session

SERVICE_TEMPLATE = """\
[Unit]
Description=minutes - auto-record meetings
After=pipewire-pulse.service

[Service]
ExecStart={exe} daemon
Environment=PATH={path}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def cmd_daemon(args, cfg):
    from minutes import daemon

    daemon.run(cfg)


def cmd_record(args, cfg):
    path = session.record(cfg, app=args.app, title=args.title, mic_source=args.mic_source, auto=args.auto)
    if path:
        print(path)


def cmd_stop(args, cfg):
    state = session.current()
    if not state:
        sys.exit("minutes: not recording")
    os.kill(state["pid"], signal.SIGINT)
    for _ in range(50):
        if not session.current():
            break
        time.sleep(0.1)
    print(f"stopped; transcribing in the background -> {cfg.output_dir}")


def cmd_toggle(args, cfg):
    if session.current():
        return cmd_stop(args, cfg)
    subprocess.Popen(
        [sys.executable, "-m", "minutes", "record"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("recording started")


def cmd_status(args, cfg):
    from minutes.detect import find_meeting

    state = session.current()
    if state:
        print(f"recording: {state['app']} since {state['started']} (pid {state['pid']})")
    else:
        print("idle")
    meeting = find_meeting(cfg.apps)
    print(f"meeting app on mic: {meeting.app} ({meeting.source})" if meeting else "meeting app on mic: none")


def cmd_process(args, cfg):
    print(session.process(Path(args.session_dir).expanduser().resolve(), cfg))


def cmd_summarize(args, cfg):
    from minutes.summarize import summarize_file

    print(summarize_file(Path(args.file).expanduser().resolve(), cfg))


def cmd_config(args, cfg):
    print(f"# {config.CONFIG_PATH}{'' if config.CONFIG_PATH.exists() else ' (not created; defaults)'}")
    for key, value in asdict(cfg).items():
        if key != "summary_prompt":
            print(f"{key} = {value!r}")


def cmd_install_service(args, cfg):
    exe = shutil.which("minutes") or sys.argv[0]
    unit = Path.home() / ".config/systemd/user/minutes.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    # Bake in the current PATH so the service can find parecord, claude, notify-send, etc.
    unit.write_text(SERVICE_TEMPLATE.format(exe=Path(exe).resolve(), path=os.environ.get("PATH", "")))
    print(f"wrote {unit}\nenable with: systemctl --user daemon-reload && systemctl --user enable --now minutes")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="minutes", description="Local-first meeting recorder.")
    parser.add_argument("--version", action="version", version=f"minutes {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("daemon", help="watch for meetings and record them automatically").set_defaults(func=cmd_daemon)

    p = sub.add_parser("record", help="record now (foreground) until Ctrl-C or `minutes stop`")
    p.add_argument("--title", help="meeting title (otherwise Claude suggests one)")
    p.add_argument("--app", default="manual", help=argparse.SUPPRESS)
    p.add_argument("--mic-source", help="PulseAudio/PipeWire source name (default: system default mic)")
    p.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_record)

    sub.add_parser("stop", help="stop the current recording").set_defaults(func=cmd_stop)
    sub.add_parser("toggle", help="start or stop a recording in the background (for keybinds)").set_defaults(func=cmd_toggle)
    sub.add_parser("status", help="show recording state and detected meeting app").set_defaults(func=cmd_status)

    p = sub.add_parser("process", help="(re)transcribe a saved audio session directory")
    p.add_argument("session_dir")
    p.set_defaults(func=cmd_process)

    p = sub.add_parser("summarize", help="(re)generate the summary for a meeting file")
    p.add_argument("file")
    p.set_defaults(func=cmd_summarize)

    sub.add_parser("config", help="show effective configuration").set_defaults(func=cmd_config)
    sub.add_parser("install-service", help="install a systemd user service for the daemon").set_defaults(func=cmd_install_service)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s minutes: %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("minutes").setLevel(logging.DEBUG if args.verbose else logging.INFO)
    args.func(args, config.load())
