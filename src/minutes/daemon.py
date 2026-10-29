"""Background loop: start a recording when a meeting app grabs the mic, stop when it lets go."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time

from minutes import session
from minutes.config import Config
from minutes.detect import find_meeting

log = logging.getLogger("minutes")


def run(cfg: Config) -> None:
    log.info("watching for meetings: %s", ", ".join(cfg.apps))
    children: list[subprocess.Popen] = []
    present_since: float | None = None
    absent_since: float | None = None
    we_started = False  # the active recording was started by us
    suppressed = False  # user stopped our recording; wait for the mic to be released

    while True:
        children = [c for c in children if c.poll() is None]  # reap finished sessions
        now = time.monotonic()
        meeting = find_meeting(cfg.apps)
        active = session.current()

        if we_started and active is None:
            we_started = False
            if meeting:  # stopped by hand mid-meeting: don't immediately restart
                suppressed = True

        if meeting:
            absent_since = None
            if active is None and not suppressed:
                present_since = present_since or now
                if now - present_since >= cfg.start_delay:
                    log.info("%s is using %s; starting recording", meeting.app, meeting.source)
                    cmd = [sys.executable, "-m", "minutes", "record", "--auto", "--app", meeting.app]
                    if meeting.source:
                        cmd += ["--mic-source", meeting.source]
                    children.append(subprocess.Popen(cmd, start_new_session=True))
                    we_started = True
                    present_since = None
                    _wait_for_state()
        else:
            present_since = None
            suppressed = False
            if active and active.get("auto") and we_started:
                absent_since = absent_since or now
                if now - absent_since >= cfg.stop_delay:
                    log.info("meeting ended; stopping recording")
                    os.kill(active["pid"], signal.SIGINT)
                    absent_since = None

        time.sleep(cfg.poll_interval)


def _wait_for_state(timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while session.current() is None and time.monotonic() < deadline:
        time.sleep(0.1)
