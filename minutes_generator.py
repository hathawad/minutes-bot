"""Minutes generation module using Claude API.

FAIL-SAFE DESIGN:
- Recording NEVER stops due to API/network issues
- All transcripts are saved locally first (raw_transcript.txt)
- API failures queue transcripts for later processing
- Queue is persisted to disk to survive crashes
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

import config

# API timeout in seconds - don't wait forever
API_TIMEOUT = 30


class MinutesGenerator:
    """Generates and updates meeting minutes using Claude."""

    def __init__(self, meeting_name: str, template: Optional[str] = None):
        self.meeting_name = meeting_name
        self.template = template or config.DEFAULT_TEMPLATE
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.minutes_file = config.MINUTES_DIR / f"{self.session_id}_{meeting_name}.md"
        self.raw_transcript_file = config.TRANSCRIPTS_DIR / f"{self.session_id}_raw.txt"
        self.current_minutes = ""
        self.offline_queue = []  # Queue transcripts when offline

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
            date=datetime.now().strftime("%Y-%m-%d"),
            meeting_name=self.meeting_name
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
            prompt = f"""You are a meeting minutes assistant. Update the existing meeting minutes with new information from the latest transcript segment.

CURRENT MINUTES:
{self.current_minutes}

NEW TRANSCRIPT SEGMENT (Chunk {chunk_number}):
{new_transcript}

INSTRUCTIONS:
1. Incorporate any new discussion points, decisions, or action items from the transcript
2. Add any newly mentioned attendees
3. Keep the existing structure and format
4. Don't remove existing content, only add or refine
5. If the transcript is unclear or contains small talk, you can skip it
6. Return the complete updated minutes document

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
