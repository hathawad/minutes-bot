"""Transcription module using whisper-cpp CLI."""

import subprocess
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

import config


def parse_whisper_timestamp(ts_str: str) -> timedelta:
    """Parse whisper timestamp like '00:01:23.456' to timedelta."""
    parts = ts_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def format_wall_time(base_time: datetime, offset: timedelta) -> str:
    """Format as wall clock time like '11:43 AM'."""
    actual_time = base_time + offset
    return actual_time.strftime("%-I:%M %p")

# Model path for whisper-cpp ggml models
WHISPER_CPP_MODEL_DIR = Path.home() / ".cache" / "whisper-cpp"

# Map friendly names to ggml model files
MODEL_MAP = {
    "tiny": "ggml-tiny.en.bin",
    "base": "ggml-base.en.bin",
    "small": "ggml-small.en.bin",
    "medium": "ggml-medium.en.bin",
    "large": "ggml-large.bin",
}


class Transcriber:
    """Transcribes audio files using whisper-cpp."""

    def __init__(self, model: str = config.WHISPER_MODEL):
        self.model = model
        self.transcripts_dir = config.TRANSCRIPTS_DIR
        self.model_path = WHISPER_CPP_MODEL_DIR / MODEL_MAP.get(model, f"ggml-{model}.bin")

    def transcribe(
        self,
        audio_path: Path,
        output_dir: Optional[Path] = None,
        chunk_start_time: Optional[datetime] = None
    ) -> dict:
        """
        Transcribe an audio file using whisper-cpp CLI.

        Args:
            audio_path: Path to the audio file
            output_dir: Where to save transcript files
            chunk_start_time: When this chunk started recording (for wall clock times)

        Returns dict with:
            - 'text': Plain text transcript
            - 'timestamped_text': Text with wall clock timestamps like "[11:43 AM] Hello..."
            - 'segments': List of (start_time, end_time, text) tuples
        """
        if output_dir is None:
            output_dir = self.transcripts_dir

        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.model_path.exists():
            return {"text": "", "timestamped_text": "", "segments": [], "error": f"Model not found: {self.model_path}"}

        cmd = [
            "whisper-cli",
            "-m", str(self.model_path),
            "-f", str(audio_path),
            "-l", config.WHISPER_LANGUAGE,
        ]

        print(f"Transcribing: {audio_path.name} (model: {self.model})")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                print(f"  Warning: {result.stderr[:200]}")
                return {"text": "", "timestamped_text": "", "segments": [], "error": result.stderr}

        except subprocess.TimeoutExpired:
            return {"text": "", "timestamped_text": "", "segments": [], "error": "Transcription timed out"}

        # Parse output - whisper-cpp outputs lines like:
        # [00:00:00.000 --> 00:00:02.980]   Test, test, one, two, three.
        text_lines = []
        timestamped_lines = []
        segments = []

        for line in result.stdout.split("\n"):
            match = re.match(r'\[(\d+:\d+:\d+\.\d+) --> (\d+:\d+:\d+\.\d+)\]\s*(.*)', line)
            if match:
                start_ts = match.group(1)
                end_ts = match.group(2)
                text_content = match.group(3).strip()

                if text_content:
                    text_lines.append(text_content)

                    # Parse timestamps
                    start_offset = parse_whisper_timestamp(start_ts)
                    end_offset = parse_whisper_timestamp(end_ts)

                    # Convert to wall clock time if we have a start time
                    if chunk_start_time:
                        wall_time = format_wall_time(chunk_start_time, start_offset)
                        timestamped_lines.append(f"[{wall_time}] {text_content}")
                    else:
                        timestamped_lines.append(f"[{start_ts}] {text_content}")

                    segments.append((start_ts, end_ts, text_content))

        text = " ".join(text_lines)
        timestamped_text = "\n".join(timestamped_lines)
        print(f"  Done: {len(text)} chars")

        # Save transcript to file
        txt_output = output_dir / f"{audio_path.stem}.txt"
        with open(txt_output, "w") as f:
            f.write(timestamped_text if timestamped_text else text)

        return {
            "text": text,
            "timestamped_text": timestamped_text,
            "segments": segments
        }

    def transcribe_session(self, session_dir: Path) -> str:
        """Transcribe all chunks in a session directory."""
        chunks = sorted(session_dir.glob("chunk_*.wav"))
        all_text = []

        for chunk in chunks:
            result = self.transcribe(chunk)
            if result.get("text"):
                all_text.append(result["text"])

        return "\n\n".join(all_text)


class TranscriptManager:
    """Manages accumulated transcripts for a session."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        # Nest transcripts by session_id like audio recordings
        self.session_dir = config.TRANSCRIPTS_DIR / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.transcript_file = self.session_dir / "full_transcript.txt"
        self.chunks_processed = 0

    def append(self, text: str, chunk_number: int):
        """Append new transcript text."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        header = f"\n\n--- Chunk {chunk_number} [{timestamp}] ---\n"

        with open(self.transcript_file, "a") as f:
            f.write(header + text)

        # Also save individual chunk file
        chunk_file = self.session_dir / f"chunk_{chunk_number:04d}.txt"
        with open(chunk_file, "w") as f:
            f.write(text)

        self.chunks_processed += 1
        print(f"  Transcript updated: {self.transcript_file}")

    def get_full_transcript(self) -> str:
        """Get the full accumulated transcript."""
        if self.transcript_file.exists():
            return self.transcript_file.read_text()
        return ""


def test_transcription():
    """Test transcription with the mic test file."""
    test_file = config.AUDIO_DIR / "mic_test.wav"
    if not test_file.exists():
        print("No test file found. Run recorder.py first.")
        return

    t = Transcriber()
    result = t.transcribe(test_file)
    print(f"\nTranscription result:\n{result.get('text', 'No text')}")


if __name__ == "__main__":
    test_transcription()
