# minutes

A local-first meeting recorder for Linux. It notices when you join a call in Zoom, Google Meet, Slack, Teams or another app, records your mic and your computer's audio, transcribes on-device with Whisper, and saves a Markdown file you can grep, sync or hand to [Claude Code](https://claude.com/claude-code).

No bot joins your meeting, and no audio leaves your machine. Summaries are optional: they run through `claude -p` on your existing Claude subscription.

```markdown
---
title: Q4 roadmap sync
date: 2026-10-29T14:30:00-07:00
app: zoom
duration: 00:42:10
---

# Q4 roadmap sync

## Summary
### Overview
...
### Action items
- [ ] Me: send the revised timeline

## Transcript

**[00:00:04] Them:** Can everyone hear me?

**[00:00:07] Me:** Yep, loud and clear.
```

## How it works

1. **Detect.** `minutes daemon` polls PipeWire (via `pactl`) for apps capturing from a microphone. When one matches the `apps` list (zoom, chrome, firefox, slack, …) for a few seconds, recording starts. When the app releases the mic, recording stops.
2. **Capture.** Two `parecord` streams are recorded as separate 16 kHz mono tracks: the mic the meeting app uses ("Me") and the default output's monitor ("Them").
3. **Transcribe.** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) transcribes each track on the CPU. The segments are merged by timestamp into a speaker-labelled transcript. Mic segments that just repeat the other side (speaker bleed when you're not wearing headphones) are dropped.
4. **Match the calendar.** If you've added calendar feeds, the event happening when the recording started supplies the meeting title and attendee list.
5. **Summarize.** `claude -p` adds an overview, decisions and action items, using attendee names where it can. If no calendar event matched, Claude also suggests a title and the file is renamed to match.

Output goes to `~/Meetings/YYYY-MM-DD-HHMM-<title>.md`. Audio is kept in `~/.local/share/minutes/sessions/` by default, so you can re-transcribe it with a better model later.

## Requirements

- Linux with PipeWire (`pipewire-pulse`) or PulseAudio: provides `pactl` and `parecord`
- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Optional: [Claude Code](https://claude.com/claude-code) (`claude` on your PATH) for summaries
- Optional: `notify-send` for desktop notifications

## Install

```sh
uv tool install git+https://github.com/KirklandGee/minutes
minutes install-service
systemctl --user daemon-reload && systemctl --user enable --now minutes
```

The first transcription downloads the Whisper model (~500 MB for `small.en`).

## Usage

```sh
minutes status            # recording state + which meeting app (if any) holds the mic
minutes record            # record now, in the foreground, until Ctrl-C
minutes record --title "1:1 with Sam"
minutes toggle            # start/stop in the background (bind this to a key)
minutes stop
minutes process ~/.local/share/minutes/sessions/2026-10-29-143000-zoom   # re-transcribe
minutes summarize ~/Meetings/2026-10-29-1430-zoom-meeting.md           # re-summarize
journalctl --user -u minutes -f                                         # daemon logs
```

Hyprland keybind for manual recording:

```
bindd = SUPER ALT, R, Toggle meeting recording, exec, minutes toggle
```

## Configuration

`~/.config/minutes/config.toml` (all keys optional; `minutes config` prints the effective values):

```toml
output_dir = "~/Meetings"
keep_audio = true
model = "small.en"        # tiny.en | base.en | small.en | medium.en | large-v3 | distil-large-v3
language = "en"           # "" to auto-detect (use a multilingual model)
summarize = true
apps = ["zoom", "chrome", "firefox", "slack", "teams"]
start_delay = 3           # seconds an app must hold the mic before recording starts
stop_delay = 20           # seconds after release before recording stops
min_duration = 30         # auto-recordings shorter than this are discarded
summary_prompt = """..."""  # customise the summary format
calendars = ["https://calendar.google.com/calendar/ical/.../basic.ics"]
calendar_email = "you@example.com"   # skip overlapping events you declined
calendar_window = 15                 # minutes before an event a recording may start
```

## Calendar titles and attendees

`calendars` takes iCal feed URLs or local `.ics` paths. You can list several, for example work and personal.

**Google Calendar:** go to Settings → *your calendar* → Integrate calendar, and copy the **Secret address in iCal format**. It needs no OAuth app or API key. Treat the URL like a password: anyone who has it can read the calendar. `minutes config` doesn't print it, and it never appears in logs. (Some Google Workspace admins turn this address off.)

How a recording is matched to an event:

- **Eligible events:** in progress when recording started, or starting within `calendar_window` minutes.
- **Skipped:** all-day, cancelled and declined events.
- **Recurring events:** expanded correctly.
- **Tie-breaks:** events with a Zoom, Meet, Teams or similar link win over plain blocks like "Focus time"; after that, the event whose start is closest wins.

Feeds are cached, so matching still works offline. To check the setup:

```sh
minutes calendar                         # what would match right now
minutes calendar --at 2026-10-29T14:00
```

A calendar title (or a `--title` you pass yourself) is never replaced by Claude's suggested title.

## Using transcripts with Claude Code

Every meeting is a plain Markdown file, so you can do things like:

```sh
cd ~/Meetings && claude "what did I commit to in meetings this week?"
```

## Caveats

- **Consent.** Recording laws differ by place, and many require everyone on the call to agree. Tell people you're taking notes.
- Browsers are matched as a whole. Any site that uses your mic in Chrome or Firefox will trigger a recording. Trim the `apps` list if that's too broad, and auto-recordings under `min_duration` are discarded anyway.
- "Them" is everything coming out of your speakers, including notification sounds and music.
- If your output device changes mid-call (for example, Bluetooth headphones connect), the system track keeps recording the old device.

## License

MIT
