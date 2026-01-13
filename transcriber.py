"""Transcription module using whisper-cpp CLI."""

import subprocess
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

import config

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

    def transcribe(self, audio_path: Path, output_dir: Optional[Path] = None) -> dict:
        """
        Transcribe an audio file using whisper-cpp CLI.
        Returns dict with 'text' key.
        """
        if output_dir is None:
            output_dir = self.transcripts_dir

        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.model_path.exists():
            return {"text": "", "error": f"Model not found: {self.model_path}"}

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
                return {"text": "", "error": result.stderr}

        except subprocess.TimeoutExpired:
            return {"text": "", "error": "Transcription timed out"}

        # Parse output - whisper-cpp outputs lines like:
        # [00:00:00.000 --> 00:00:02.980]   Test, test, one, two, three.
        text_lines = []
        for line in result.stdout.split("\n"):
            match = re.match(r'\[[\d:.]+ --> [\d:.]+\]\s*(.*)', line)
            if match:
                text_lines.append(match.group(1).strip())

        text = " ".join(text_lines)
        print(f"  Done: {len(text)} chars")

        # Save transcript to file
        txt_output = output_dir / f"{audio_path.stem}.txt"
        with open(txt_output, "w") as f:
            f.write(text)

        return {"text": text}

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
        self.transcript_file = config.TRANSCRIPTS_DIR / f"{session_id}_full.txt"
        self.chunks_processed = 0

    def append(self, text: str, chunk_number: int):
        """Append new transcript text."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        header = f"\n\n--- Chunk {chunk_number} [{timestamp}] ---\n"

        with open(self.transcript_file, "a") as f:
            f.write(header + text)

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
