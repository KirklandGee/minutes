from datetime import datetime, timezone

from minutes import markdown
from minutes.detect import match_app
from minutes.summarize import split_title
from minutes.transcribe import Segment, drop_echo, merge

APPS = ["zoom", "chrome", "firefox"]


def test_match_app_by_binary():
    assert match_app({"application.process.binary": "zoom"}, APPS) == "zoom"
    assert match_app({"application.name": "Google Chrome"}, APPS) == "chrome"
    assert match_app({"application.process.binary": "spotify"}, APPS) is None


def test_match_app_ignores_self():
    assert match_app({"application.name": "minutes", "node.name": "chrome"}, APPS) is None


def test_merge_joins_same_speaker():
    segs = [
        Segment(0, 2, "Me", "Hello"),
        Segment(5, 7, "Them", "Hi there"),
        Segment(2.5, 4, "Me", "everyone."),
        Segment(20, 22, "Them", "Later."),
        Segment(8, 9, "Them", "How are you?"),
    ]
    out = merge(segs)
    assert [(s.speaker, s.text) for s in out] == [
        ("Me", "Hello everyone."),
        ("Them", "Hi there How are you?"),
        ("Them", "Later."),
    ]


def test_drop_echo_removes_speaker_bleed():
    segs = [
        Segment(10, 13, "Them", "Let's ship it on Friday."),
        Segment(10.2, 13.1, "Me", "let's ship it on friday"),
        Segment(14, 15, "Me", "Sounds good."),
    ]
    assert [s.text for s in drop_echo(segs)] == ["Let's ship it on Friday.", "Sounds good."]


def test_render_and_set_summary():
    started = datetime(2026, 10, 29, 14, 30, tzinfo=timezone.utc)
    md = markdown.render("Zoom meeting", started, "zoom", 125, [Segment(65, 70, "Me", "Hi.")], None, None)
    assert "duration: 00:02:05" in md
    assert "**[00:01:05] Me:** Hi." in md
    assert markdown.SUMMARY_PLACEHOLDER in md

    updated = markdown.set_summary(md, "### Overview\nWe talked.", "Roadmap sync")
    assert markdown.field(updated, "title") == "Roadmap sync"
    assert markdown.field(updated, "title_source") == "claude"
    assert "# Roadmap sync" in updated
    assert markdown.SUMMARY_PLACEHOLDER not in updated
    assert "### Overview\nWe talked.\n\n## Transcript" in updated
    assert markdown.transcript_text(updated) == "**[00:01:05] Me:** Hi."


def test_output_path():
    started = datetime(2026, 10, 29, 14, 30)
    assert markdown.output_path(markdown.Path("/m"), started, "Q4 Roadmap!").name == "2026-10-29-1430-q4-roadmap.md"


def test_split_title():
    assert split_title("Title: **Roadmap sync**\n\n### Overview\nx") == ("Roadmap sync", "### Overview\nx")
    assert split_title("### Overview\nx") == (None, "### Overview\nx")
