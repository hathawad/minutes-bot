"""Minutes generation module using Claude API.

FAIL-SAFE DESIGN:
- Recording NEVER stops due to API/network issues
- All transcripts are saved locally first (raw_transcript.txt)
- API failures queue transcripts for later processing
- Queue is persisted to disk to survive crashes
"""

import os
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

import config


def read_file_content(file_path: Path) -> str:
    """Read file content, converting .docx files using textutil."""
    if file_path.suffix.lower() == '.docx':
        try:
            result = subprocess.run(
                ['textutil', '-convert', 'txt', '-stdout', str(file_path)],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout
        except Exception as e:
            print(f"  [Warning] Could not read {file_path.name}: {e}")
            return ""
    else:
        try:
            return file_path.read_text()
        except Exception as e:
            print(f"  [Warning] Could not read {file_path.name}: {e}")
            return ""


def load_agenda() -> tuple[str, bool]:
    """
    Load agenda from agendas folder.
    Returns (agenda_text, has_multiple_warning).
    """
    agenda_files = [f for f in config.AGENDAS_DIR.iterdir()
                    if f.is_file() and not f.name.startswith('.')]

    if not agenda_files:
        return "", False

    has_multiple = len(agenda_files) > 1

    # Use the most recently modified agenda
    agenda_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    agenda_content = read_file_content(agenda_files[0])

    return agenda_content, has_multiple


def load_sample_minutes() -> str:
    """Load all sample minutes from samples folder."""
    sample_files = [f for f in config.SAMPLES_DIR.iterdir()
                    if f.is_file() and not f.name.startswith('.')]

    if not sample_files:
        return ""

    samples = []
    for f in sorted(sample_files, key=lambda x: x.stat().st_mtime, reverse=True):
        content = read_file_content(f)
        if content:
            samples.append(f"=== Sample: {f.name} ===\n{content}")

    return "\n\n".join(samples)

# API timeout in seconds - don't wait forever
API_TIMEOUT = 30


class MinutesGenerator:
    """Generates and updates meeting minutes using Claude."""

    def __init__(self, meeting_name: str, session_id: Optional[str] = None, template: Optional[str] = None):
        self.meeting_name = meeting_name
        self.template = template or config.DEFAULT_TEMPLATE
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_start = datetime.now()
        self.session_end: Optional[datetime] = None
        self.minutes_file = config.MINUTES_DIR / f"{self.session_id}_{meeting_name}.md"

        # Nest raw transcripts by session_id like audio
        self.transcript_dir = config.TRANSCRIPTS_DIR / self.session_id
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        self.raw_transcript_file = self.transcript_dir / "raw_backup.txt"

        self.current_minutes = ""
        self.offline_queue = []  # Queue transcripts when offline

        # Load agenda and samples for context
        self.agenda, has_multiple_agendas = load_agenda()
        self.sample_minutes = load_sample_minutes()

        if has_multiple_agendas:
            print(f"  [Warning] Multiple agendas found in agendas/ folder. Using most recent.")
        if self.agenda:
            print(f"  [Info] Loaded agenda for meeting structure")
        if self.sample_minutes:
            print(f"  [Info] Loaded sample minutes for style reference")

        # Try to create client, but don't fail if we can't
        self.client = None
        if ANTHROPIC_AVAILABLE and config.ANTHROPIC_API_KEY:
            try:
                self.client = anthropic.Anthropic(
                    api_key=config.ANTHROPIC_API_KEY,
                    timeout=API_TIMEOUT
                )
            except Exception as e:
                print(f"  [Warning] Could not initialize API client: {e}")

    def _init_minutes(self):
        """Initialize minutes from template."""
        self.current_minutes = self.template.format(
            date=self.session_start.strftime("%Y-%m-%d"),
            meeting_name=self.meeting_name,
            start_time=self.session_start.strftime("%-I:%M %p"),
            end_time="(in progress)"
        )
        self._save()

    def finalize(self):
        """Mark the session as ended and update the end time in minutes."""
        self.session_end = datetime.now()
        if self.current_minutes:
            self.current_minutes = self.current_minutes.replace(
                "**Ended:** (in progress)",
                f"**Ended:** {self.session_end.strftime('%-I:%M %p')}"
            )
            self._save()

    def _save(self):
        """Save current minutes to file."""
        with open(self.minutes_file, "w") as f:
            f.write(self.current_minutes)

    def _save_raw_transcript(self, text: str, chunk_number: int):
        """
        FAIL-SAFE: Always save raw transcript to disk first.
        This ensures we never lose data, even if everything else fails.
        """
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            with open(self.raw_transcript_file, "a") as f:
                f.write(f"\n\n--- Chunk {chunk_number} [{timestamp}] ---\n")
                f.write(text)
        except Exception as e:
            # Even if this fails, don't crash - just warn
            print(f"  [Warning] Could not save raw transcript: {e}")

    def _queue_transcript(self, text: str, chunk_number: int, reason: str = "offline"):
        """Queue a transcript for later processing."""
        self.offline_queue.append({
            "chunk": chunk_number,
            "text": text,
            "timestamp": datetime.now().isoformat(),
            "reason": reason
        })
        print(f"  [Queued] {reason} (queue size: {len(self.offline_queue)})")

    def update_minutes(self, new_transcript: str, chunk_number: int) -> bool:
        """
        Update minutes with new transcript content.
        Returns True if successful, False if queued for later (offline).

        FAIL-SAFE: This method will NEVER raise an exception.
        All errors result in queuing for later processing.
        """
        # ALWAYS save raw transcript first - this is our backup
        self._save_raw_transcript(new_transcript, chunk_number)

        if not self.current_minutes:
            try:
                self._init_minutes()
            except Exception as e:
                print(f"  [Warning] Could not init minutes template: {e}")

        if not self.client:
            self._queue_transcript(new_transcript, chunk_number, "no API client")
            return False

        try:
            # Build context sections
            context_parts = []

            if self.sample_minutes:
                context_parts.append(f"""STYLE REFERENCE (match this format and tone):
{self.sample_minutes}""")

            if self.agenda:
                context_parts.append(f"""MEETING AGENDA (use this to organize topics):
{self.agenda}""")

            context_section = "\n\n".join(context_parts)

            prompt = f"""You are a meeting minutes assistant. Update the existing meeting minutes with new information from the latest transcript segment.

{context_section}

CURRENT MINUTES:
{self.current_minutes}

NEW TRANSCRIPT SEGMENT (Chunk {chunk_number}):
{new_transcript}

INSTRUCTIONS:
1. Incorporate any new discussion points, decisions, or action items from the transcript
2. Add any newly mentioned attendees
3. Match the style and format of the sample minutes if provided
4. Organize content according to the agenda topics if provided
5. Keep the existing structure and format
6. Don't remove existing content, only add or refine
7. If the transcript is unclear or contains small talk, you can skip it
8. Return the complete updated minutes document

Return ONLY the updated minutes markdown, no explanations."""

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )

            self.current_minutes = response.content[0].text
            self._save()
            print(f"  Minutes updated: {self.minutes_file}")
            return True

        except Exception as e:
            # Identify the error type for better messaging
            error_name = type(e).__name__
            if "Connection" in error_name or "connection" in str(e).lower():
                reason = "no internet connection"
            elif "RateLimit" in error_name or "rate" in str(e).lower():
                reason = "rate limited"
            elif "Timeout" in error_name or "timeout" in str(e).lower():
                reason = "API timeout"
            else:
                reason = f"{error_name}: {str(e)[:50]}"

            self._queue_transcript(new_transcript, chunk_number, reason)
            return False

    def process_queue(self) -> int:
        """Process queued transcripts when back online. Returns count processed."""
        if not self.client or not self.offline_queue:
            return 0

        # Combine all queued transcripts
        combined = "\n\n".join(
            f"[Chunk {item['chunk']}]\n{item['text']}"
            for item in self.offline_queue
        )

        queue_size = len(self.offline_queue)
        self.offline_queue = []

        if self.update_minutes(combined, -1):  # -1 indicates batch update
            print(f"  Processed {queue_size} queued transcripts")
            return queue_size
        return 0

    def get_minutes(self) -> str:
        """Get the current minutes content."""
        if self.minutes_file.exists():
            return self.minutes_file.read_text()
        return self.current_minutes or ""


class OfflineMinutesStore:
    """Stores transcripts locally when offline for later processing."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.store_file = config.DATA_DIR / f"{session_id}_offline_queue.json"

    def save_queue(self, queue: list):
        """Persist queue to disk."""
        import json
        with open(self.store_file, "w") as f:
            json.dump(queue, f)

    def load_queue(self) -> list:
        """Load queue from disk."""
        import json
        if self.store_file.exists():
            with open(self.store_file) as f:
                return json.load(f)
        return []


if __name__ == "__main__":
    # Test with a sample transcript
    if not config.ANTHROPIC_API_KEY:
        print("Set ANTHROPIC_API_KEY to test minutes generation")
    else:
        gen = MinutesGenerator("Test Meeting")
        gen.update_minutes(
            "John said we need to finish the quarterly report by Friday. "
            "Mary agreed and said she would handle the financial section.",
            chunk_number=1
        )
        print("\nGenerated minutes:")
        print(gen.get_minutes())
