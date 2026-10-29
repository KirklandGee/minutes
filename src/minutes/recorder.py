"""Capture mic and system audio as two separate 16 kHz mono tracks using parecord."""

from __future__ import annotations

import signal
import subprocess
import time
import wave
from pathlib import Path

from minutes.detect import OWN_CLIENT_NAME

RATE = 16000
TRACKS = {"mic": "@DEFAULT_SOURCE@", "system": "@DEFAULT_MONITOR@"}


class Recorder:
    def __init__(self, session_dir: Path, mic_source: str | None = None):
        self.session_dir = session_dir
        self.devices = dict(TRACKS, mic=mic_source or TRACKS["mic"])
        self.procs: dict[str, subprocess.Popen] = {}

    def raw_path(self, track: str) -> Path:
        return self.session_dir / f"{track}.raw"

    def wav_path(self, track: str) -> Path:
        return self.session_dir / f"{track}.wav"

    def start(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        for track, device in self.devices.items():
            self.procs[track] = subprocess.Popen(
                [
                    "parecord", "--raw", f"--client-name={OWN_CLIENT_NAME}",
                    f"--device={device}", f"--rate={RATE}", "--channels=1", "--format=s16le",
                    str(self.raw_path(track)),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        time.sleep(0.5)
        for track, proc in self.procs.items():
            if proc.poll() is not None:
                self.stop()
                raise RuntimeError(f"parecord ({track}) failed: {proc.stderr.read().strip()}")

    def stop(self) -> dict[str, Path]:
        """Stop capture and convert each raw track to WAV. Returns {track: wav_path}."""
        for proc in self.procs.values():
            proc.send_signal(signal.SIGINT)
        for proc in self.procs.values():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        wavs = {}
        for track in self.procs:
            raw = self.raw_path(track)
            if raw.exists():
                raw_to_wav(raw, self.wav_path(track))
                raw.unlink()
                wavs[track] = self.wav_path(track)
        return wavs


def raw_to_wav(raw: Path, wav_path: Path) -> None:
    with raw.open("rb") as src, wave.open(str(wav_path), "wb") as dst:
        dst.setnchannels(1)
        dst.setsampwidth(2)
        dst.setframerate(RATE)
        while chunk := src.read(1 << 20):
            dst.writeframes(chunk)


def duration(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as w:
        return w.getnframes() / w.getframerate()
