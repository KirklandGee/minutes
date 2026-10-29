"""Find the calendar event a recording belongs to, from iCal (.ics) feeds.

For Google Calendar, use the calendar's "Secret address in iCal format"
(Settings -> your calendar -> Integrate calendar). No OAuth app needed.
"""

from __future__ import annotations

import hashlib
import logging
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from minutes.config import DATA_DIR, Config

log = logging.getLogger("minutes")
CACHE_DIR = DATA_DIR / "calendar-cache"
CONFERENCE_HINTS = (
    "zoom.us", "meet.google.com", "teams.microsoft.com", "teams.live.com",
    "webex.com", "slack.com", "whereby.com", "around.co", "discord.gg",
)


@dataclass
class Event:
    title: str
    start: datetime
    end: datetime
    attendees: list[str] = field(default_factory=list)
    has_link: bool = False


def find_event(cfg: Config, at: datetime) -> Event | None:
    """The event most likely to be the meeting that started recording at `at`."""
    events: list[Event] = []
    for source in cfg.calendars:
        try:
            events += events_near(load_ics(source), at, cfg.calendar_email)
        except Exception as e:  # a broken feed shouldn't break transcription
            log.warning("calendar %s: %s", urlparse(source).netloc or source, e)
    return best_match(events, at, timedelta(minutes=cfg.calendar_window))


def load_ics(source: str) -> bytes:
    """Read a local .ics file, or fetch a feed URL (falling back to the last good copy offline)."""
    if not source.startswith(("http://", "https://", "webcal://")):
        return Path(source).expanduser().read_bytes()
    url = "https://" + source.removeprefix("webcal://") if source.startswith("webcal://") else source
    # Secret feed URLs are credentials: cache under a hash, never log them.
    cache = CACHE_DIR / f"{hashlib.sha256(source.encode()).hexdigest()[:16]}.ics"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = resp.read()
    except OSError as e:
        if not cache.exists():
            raise
        log.warning("calendar fetch failed (%s); using cached copy", e)
        return cache.read_bytes()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def events_near(ics: bytes, at: datetime, email: str | None = None) -> list[Event]:
    """Timed, non-cancelled, non-declined events (recurrences expanded) within 12h of `at`."""
    import icalendar
    import recurring_ical_events

    cal = icalendar.Calendar.from_ical(ics)
    window = timedelta(hours=12)
    events = []
    for comp in recurring_ical_events.of(cal).between(at - window, at + window):
        start, end = comp.start, comp.end
        if not isinstance(start, datetime) or str(comp.get("STATUS", "")).upper() == "CANCELLED":
            continue  # all-day events are dates, not datetimes
        attendees, declined = [], False
        raw = comp.get("ATTENDEE", [])
        for a in raw if isinstance(raw, list) else [raw]:
            if a.params.get("CUTYPE", "INDIVIDUAL").upper() in ("RESOURCE", "ROOM"):
                continue
            addr = str(a).split(":", 1)[-1]
            if email and addr.lower() == email.lower():
                declined = a.params.get("PARTSTAT", "").upper() == "DECLINED"
            attendees.append(a.params.get("CN") or addr)
        if declined:
            continue
        text = " ".join(
            str(comp.get(k, "")) for k in ("LOCATION", "DESCRIPTION", "URL", "X-GOOGLE-CONFERENCE")
        ).lower()
        events.append(Event(
            title=str(comp.get("SUMMARY", "")).strip() or "Untitled event",
            start=_aware(start),
            end=_aware(end) if isinstance(end, datetime) else _aware(start) + timedelta(hours=1),
            attendees=attendees,
            has_link=any(h in text for h in CONFERENCE_HINTS),
        ))
    return events


def best_match(events: list[Event], at: datetime, window: timedelta) -> Event | None:
    """Events in progress at `at` (or starting within `window`), preferring ones with a
    meeting link, then the one whose start is closest."""
    candidates = [e for e in events if e.start - window <= at < e.end]
    if not candidates:
        return None
    return min(candidates, key=lambda e: (not e.has_link, abs((at - e.start).total_seconds())))


def _aware(dt: datetime | date) -> datetime:
    return dt if dt.tzinfo else dt.astimezone()  # floating times are local
