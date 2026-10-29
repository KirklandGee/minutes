"""Transcribe each track with faster-whisper and merge them into a speaker-labelled transcript."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from minutes.config import Config

SPEAKERS = {"mic": "Me", "system": "Them"}


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
        result, _info = model.transcribe(
            load_wav(path), language=cfg.language or None, beam_size=cfg.beam_size, vad_filter=True
        )
        for s in result:
            text = s.text.strip()
            if text:
                segments.append(Segment(s.start, s.end, SPEAKERS.get(track, track), text))
    return merge(drop_echo(segments))


def load_wav(path: Path):
    """Read our 16 kHz mono s16 WAVs straight into the float array whisper wants (skips PyAV)."""
    import numpy as np

    with wave.open(str(path), "rb") as w:
        pcm = w.readframes(w.getnframes())
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0


def drop_echo(segments: list[Segment], threshold: float = 0.6) -> list[Segment]:
    """Drop mic segments that are just the other side bleeding through speakers into the mic."""
    them = [s for s in segments if s.speaker == "Them"]

    def is_echo(seg: Segment) -> bool:
        return any(
            t.start < seg.end + 1 and seg.start < t.end + 1
            and SequenceMatcher(None, seg.text.lower(), t.text.lower()).ratio() >= threshold
            for t in them
        )

    return [s for s in segments if s.speaker != "Me" or not is_echo(s)]


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
