"""Transcribe each track with faster-whisper and merge them into a speaker-labelled transcript."""

from __future__ import annotations

import re
import wave
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from minutes.config import Config

SPEAKERS = {"mic": "Me", "system": "Them"}
# Audio is decoded and transcribed this many seconds at a time, so memory stays flat for long meetings.
CHUNK_SECONDS = 600


@dataclass
class Segment:
    start: float
    end: float
    speaker: str
    text: str


def transcribe(wavs: dict[str, Path], cfg: Config) -> list[Segment]:
    from faster_whisper import WhisperModel  # slow import; keep it off the CLI startup path

    model = WhisperModel(cfg.model, device="cpu", compute_type=cfg.compute_type)
    segments: list[Segment] = []
    for track, path in wavs.items():
        for offset, audio in wav_chunks(path):
            result, _info = model.transcribe(
                audio, language=cfg.language or None, beam_size=cfg.beam_size, vad_filter=True
            )
            for s in result:
                text = s.text.strip()
                if text:
                    segments.append(Segment(offset + s.start, offset + s.end, SPEAKERS.get(track, track), text))
    return merge(drop_echo(segments))


def wav_chunks(path: Path, size: float = CHUNK_SECONDS, search: float = 20.0):
    """Yield (offset seconds, float audio) pieces of our 16 kHz mono s16 WAVs (read directly; skips PyAV).

    Each piece ends at the quietest moment in its last `search` seconds, so words aren't cut in half.
    """
    import numpy as np

    with wave.open(str(path), "rb") as w:
        rate, total = w.getframerate(), w.getnframes()
        start, carry = 0, np.empty(0, dtype=np.int16)
        while True:
            fresh = np.frombuffer(w.readframes(int(size * rate) - len(carry)), dtype=np.int16)
            pcm = np.concatenate([carry, fresh])
            if start + len(pcm) >= total:
                if len(pcm):
                    yield start / rate, pcm.astype(np.float32) / 32768.0
                return
            tail = int(search * rate)
            cut = len(pcm) - tail + quietest(pcm[-tail:], rate)
            yield start / rate, pcm[:cut].astype(np.float32) / 32768.0
            start, carry = start + cut, pcm[cut:]


def quietest(pcm, rate: int, frame: float = 0.1) -> int:
    """Sample index at the centre of the lowest-energy `frame`-second window."""
    import numpy as np

    n = int(frame * rate)
    frames = pcm[: len(pcm) // n * n].astype(np.float32).reshape(-1, n)
    return int(np.argmin((frames**2).mean(axis=1))) * n + n // 2


def drop_echo(segments: list[Segment], threshold: float = 0.6) -> list[Segment]:
    """Drop mic segments that are just the other side bleeding through speakers into the mic."""
    them = [s for s in segments if s.speaker == "Them"]

    def is_echo(seg: Segment) -> bool:
        return any(
            t.start < seg.end + 1 and seg.start < t.end + 1 and echo_coverage(seg.text, t.text) >= threshold
            for t in them
        )

    return [s for s in segments if s.speaker != "Me" or not is_echo(s)]


def echo_coverage(mine: str, theirs: str) -> float:
    """Fraction of `mine`'s words found, in order, in `theirs` (catches short echoes of long segments)."""
    a, b = words(mine), words(theirs)
    if not a:
        return 0.0
    blocks = SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
    return sum(m.size for m in blocks) / len(a)


def words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def merge(segments: list[Segment], max_gap: float = 2.0) -> list[Segment]:
    """Sort by time and join consecutive same-speaker segments into paragraphs."""
    merged: list[Segment] = []
    for seg in sorted(segments, key=lambda s: s.start):
        prev = merged[-1] if merged else None
        if prev and prev.speaker == seg.speaker and seg.start - prev.end <= max_gap:
            prev.end = max(prev.end, seg.end)
            prev.text = f"{prev.text} {seg.text}"
        else:
            merged.append(Segment(seg.start, seg.end, seg.speaker, seg.text))
    return merged
