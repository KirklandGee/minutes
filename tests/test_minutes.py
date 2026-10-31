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



def test_drop_echo_catches_fragment_of_longer_segment():
    segs = [
        Segment(25.4, 36.9, "Them", "Cut that synergizes with your deck and you say, okay, I chibbled a bunch,"),
        Segment(35.0, 36.9, "Me", "Okay, I should have a bunch."),
        Segment(37.9, 43.7, "Them", "Now it's time for something that actually does what the deck wants to do."),
        Segment(37.9, 38.9, "Me", "Now it's..."),
        Segment(38.9, 49.5, "Me", "Yeah, that makes sense."),
    ]
    assert [s.text for s in drop_echo(segs) if s.speaker == "Me"] == ["Yeah, that makes sense."]

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


def test_wav_chunks_split_at_silence_and_cover_everything(tmp_path):
    import wave

    import numpy as np

    from minutes.transcribe import wav_chunks

    rate = 16000
    rng = np.random.default_rng(0)
    pcm = (rng.standard_normal(rate * 25) * 3000).astype(np.int16)
    pcm[rate * 7 : rate * 7 + 1600] = 0  # a quiet 0.1s at 7s, inside the search window before the 10s mark
    path = tmp_path / "t.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(pcm.tobytes())

    chunks = list(wav_chunks(path, size=10, search=5))
    assert abs(chunks[1][0] - 7.05) < 0.01
    assert sum(len(a) for _, a in chunks) == len(pcm)
    assert np.allclose(np.concatenate([a for _, a in chunks]), pcm / 32768.0)


def test_browser_ignored_while_discord_open_unless_in_a_call():
    from minutes.config import Config
    from minutes.detect import ignored_browser_use

    cfg = Config()
    discord = ("chrome-discord.com__channels_@me-default", "discord | friends")
    terminal = ("org.omarchy.terminal", "reading about discord")
    meet = ("helium", "meet - abc-defg-hij - helium")
    assert ignored_browser_use(cfg, [discord])
    assert not ignored_browser_use(cfg, [discord, meet])
    assert not ignored_browser_use(cfg, [terminal])
    assert not ignored_browser_use(cfg, None)
