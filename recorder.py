"""Audio recording module using SoX."""

import subprocess
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import config


class AudioRecorder:
    """Records audio in chunks using SoX."""

    def __init__(self, chunk_duration: int = config.CHUNK_DURATION_SECONDS):
        self.chunk_duration = chunk_duration
        self.process: Optional[subprocess.Popen] = None
        self.chunk_number = 0
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = config.AUDIO_DIR / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def get_chunk_path(self) -> Path:
        """Get the path for the current chunk."""
        return self.session_dir / f"chunk_{self.chunk_number:04d}.wav"

    def record_chunk(self) -> Path:
        """Record a single audio chunk. Returns path to recorded file."""
        output_path = self.get_chunk_path()

        cmd = [
            "sox",
            "-d",  # Default audio device (microphone)
            "-c", str(config.CHANNELS),
            "-r", str(config.SAMPLE_RATE),
            "-b", "16",  # 16-bit
            str(output_path),
            "trim", "0", str(self.chunk_duration)
        ]

        print(f"Recording chunk {self.chunk_number} ({self.chunk_duration}s)...")
        print(f"  Output: {output_path}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  Warning: {result.stderr}")
        except KeyboardInterrupt:
            print("\n  Recording interrupted by user")
            raise

        self.chunk_number += 1
        return output_path

    def start_continuous(self, callback=None):
        """Start continuous recording, calling callback after each chunk."""
        print(f"Starting continuous recording session: {self.session_id}")
        print(f"Chunk duration: {self.chunk_duration}s")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                chunk_path = self.record_chunk()
                if callback and chunk_path.exists():
                    callback(chunk_path)
        except KeyboardInterrupt:
            print("\n\nRecording session ended.")
            return self.session_dir


def test_microphone():
    """Quick test to verify microphone is working."""
    print("Testing microphone (3 second recording)...")
    test_file = config.AUDIO_DIR / "mic_test.wav"

    cmd = [
        "sox", "-d",
        "-c", "1", "-r", "16000", "-b", "16",
        str(test_file),
        "trim", "0", "3"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if test_file.exists() and test_file.stat().st_size > 1000:
        print(f"Success! Test file: {test_file}")
        print(f"File size: {test_file.stat().st_size} bytes")
        return True
    else:
        print(f"Failed. stderr: {result.stderr}")
        return False


if __name__ == "__main__":
    test_microphone()
