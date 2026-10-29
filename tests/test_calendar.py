from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from minutes import markdown
from minutes.calendar import best_match, events_near

NY = ZoneInfo("America/New_York")
WINDOW = timedelta(minutes=15)

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:test
BEGIN:VEVENT
UID:standup
SUMMARY:Daily standup
DTSTART;TZID=America/New_York:20261001T093000
DTEND;TZID=America/New_York:20261001T094500
RRULE:FREQ=DAILY
LOCATION:https://meet.google.com/abc-defg-hij
ATTENDEE;CN=Sam Lee;PARTSTAT=ACCEPTED:mailto:sam@example.com
ATTENDEE;CN=Big Room;CUTYPE=ROOM:mailto:room@example.com
ATTENDEE;PARTSTAT=ACCEPTED:mailto:me@example.com
END:VEVENT
BEGIN:VEVENT
UID:focus
SUMMARY:Focus time
DTSTART;TZID=America/New_York:20261029T090000
DTEND;TZID=America/New_York:20261029T110000
END:VEVENT
BEGIN:VEVENT
UID:declined
SUMMARY:Vendor pitch
DTSTART;TZID=America/New_York:20261029T140000
DTEND;TZID=America/New_York:20261029T150000
DESCRIPTION:Join Zoom: https://zoom.us/j/123
ATTENDEE;PARTSTAT=DECLINED:mailto:me@example.com
END:VEVENT
BEGIN:VEVENT
UID:roadmap
SUMMARY:Q4 roadmap: review
DTSTART;TZID=America/New_York:20261029T140000
DTEND;TZID=America/New_York:20261029T150000
DESCRIPTION:Join Zoom: https://zoom.us/j/456
END:VEVENT
BEGIN:VEVENT
UID:cancelled
SUMMARY:Cancelled sync
STATUS:CANCELLED
DTSTART;TZID=America/New_York:20261029T160000
DTEND;TZID=America/New_York:20261029T170000
LOCATION:https://zoom.us/j/789
END:VEVENT
BEGIN:VEVENT
UID:allday
SUMMARY:Company offsite
DTSTART;VALUE=DATE:20261029
DTEND;VALUE=DATE:20261030
END:VEVENT
END:VCALENDAR
"""


def match(hour, minute, email="me@example.com"):
    at = datetime(2026, 10, 29, hour, minute, tzinfo=NY)
    return best_match(events_near(ICS, at, email), at, WINDOW)


def test_recurring_event_with_link_beats_overlapping_block():
    event = match(9, 28)  # joined two minutes early, during "Focus time"
    assert event.title == "Daily standup"
    assert event.attendees == ["Sam Lee", "me@example.com"]  # room excluded


def test_declined_event_skipped():
    assert match(14, 5).title == "Q4 roadmap: review"
    assert match(14, 5, email=None).title in ("Q4 roadmap: review", "Vendor pitch")


def test_cancelled_and_all_day_ignored():
    assert match(16, 10) is None


def test_outside_window():
    assert match(13, 30) is None  # 30 min before roadmap, after focus time ended
    assert match(13, 50).title == "Q4 roadmap: review"


def test_calendar_title_survives_frontmatter_round_trip():
    started = datetime(2026, 10, 29, 14, 0, tzinfo=NY)
    md = markdown.render(
        "Q4 roadmap: review", started, "zoom", 60, [], None, None,
        title_source="calendar", attendees=["Sam Lee"],
    )
    assert markdown.field(md, "title") == "Q4 roadmap: review"
    assert markdown.field(md, "title_source") == "calendar"
    assert 'attendees: ["Sam Lee"]' in md
