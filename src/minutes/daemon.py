"""Background loop: offer to record when a meeting app grabs the mic, stop when it lets go."""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import time

from minutes import session
from minutes.config import Config
from minutes.detect import MicUser, find_meeting

log = logging.getLogger("minutes")


def run(cfg: Config) -> None:
    log.info("watching for meetings: %s", ", ".join(cfg.apps))
    children: list[subprocess.Popen] = []
    present_since: float | None = None
    absent_since: float | None = None
    we_started = False  # the active recording was started by us
    suppressed = False  # user stopped our recording or declined; wait for the mic to be released
    prompt: Prompt | None = None

    while True:
        children = [c for c in children if c.poll() is None]  # reap finished sessions
        now = time.monotonic()
        meeting = find_meeting(cfg)
        active = session.current()

        if we_started and active is None:
            we_started = False
            if meeting:  # stopped by hand mid-meeting: don't immediately restart
                suppressed = True

        if meeting:
            absent_since = None
            if prompt and (answer := prompt.answer()) is not None:
                prompt = None
                if answer == "record" and session.current() is None:
                    children.append(start(meeting))
                    we_started = True
            elif active is None and not suppressed and not prompt:
                present_since = present_since or now
                if now - present_since >= cfg.start_delay:
                    present_since = None
                    if cfg.ask and shutil.which("notify-send"):
                        log.info("%s is using %s; asking whether to record", meeting.app, meeting.source)
                        prompt = Prompt(meeting)
                        suppressed = True  # one question per stretch of mic use
                    else:
                        log.info("%s is using %s; starting recording", meeting.app, meeting.source)
                        children.append(start(meeting))
                        we_started = True
        else:
            present_since = None
            suppressed = False
            if prompt:  # the call ended before anyone answered
                prompt.close()
                prompt = None
            if active and active.get("auto") and we_started:
                absent_since = absent_since or now
                if now - absent_since >= cfg.stop_delay:
                    log.info("meeting ended; stopping recording")
                    os.kill(active["pid"], signal.SIGINT)
                    absent_since = None

        time.sleep(cfg.poll_interval)


def start(meeting: MicUser) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "minutes", "record", "--auto", "--app", meeting.app]
    if meeting.source:
        cmd += ["--mic-source", meeting.source]
    proc = subprocess.Popen(cmd, start_new_session=True)
    _wait_for_state()
    return proc


class Prompt:
    """A "Record this meeting?" notification with Record / Not now buttons."""

    def __init__(self, meeting: MicUser):
        self.proc = subprocess.Popen(
            ["notify-send", "-a", "minutes", "-p", "-t", "0", "--wait",
             "-A", "record=Record", "-A", "dismiss=Not now",
             "Meeting detected", f"{meeting.app.title()} is using your mic. Record it?"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        self.id = self.proc.stdout.readline().strip()  # printed as soon as it's shown

    def answer(self) -> str | None:
        """The clicked action ("" if dismissed), or None while still waiting."""
        if self.proc.poll() is None:
            return None
        return self.proc.stdout.read().strip()

    def close(self) -> None:
        self.proc.terminate()
        if self.id.isdigit():
            subprocess.run(
                ["gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications",
                 "--object-path", "/org/freedesktop/Notifications",
                 "--method", "org.freedesktop.Notifications.CloseNotification", self.id],
                capture_output=True, check=False,
            )


def _wait_for_state(timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while session.current() is None and time.monotonic() < deadline:
        time.sleep(0.1)
