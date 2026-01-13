"""Interactive recorder with spacebar control."""

import subprocess
import sys
import tty
import termios
import threading
import signal
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import config


class InteractiveRecorder:
    """Records audio with spacebar-triggered chunk boundaries."""

    def __init__(self, on_chunk_ready: Optional[Callable[[Path, int], None]] = None):
        """
        Args:
            on_chunk_ready: Callback called with (audio_path, chunk_number) when a chunk is ready.
                           This is called in a background thread.
        """
        self.on_chunk_ready = on_chunk_ready
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = config.AUDIO_DIR / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.chunk_number = 0
        self.recording_process: Optional[subprocess.Popen] = None
        self.running = False
        self._original_term_settings = None

    def _get_chunk_path(self) -> Path:
        """Get path for current chunk."""
        return self.session_dir / f"chunk_{self.chunk_number:04d}.wav"

    def _start_recording(self) -> Path:
        """Start recording to current chunk. Returns the path being recorded to."""
        output_path = self._get_chunk_path()

        cmd = [
            "sox",
            "-d",  # Default input device
            "-c", str(config.CHANNELS),
            "-r", str(config.SAMPLE_RATE),
            "-b", "16",
            str(output_path),
        ]

        # Start recording process (no duration limit - we'll kill it on spacebar)
        self.recording_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return output_path

    def _stop_recording(self) -> Optional[Path]:
        """Stop current recording. Returns path to the recorded file."""
        if self.recording_process is None:
            return None

        current_path = self._get_chunk_path()

        # Send SIGTERM for clean shutdown
        self.recording_process.terminate()
        try:
            self.recording_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.recording_process.kill()
            self.recording_process.wait()

        self.recording_process = None
        self.chunk_number += 1

        # Verify file exists and has content
        if current_path.exists() and current_path.stat().st_size > 1000:
            return current_path
        return None

    def _process_chunk_background(self, chunk_path: Path, chunk_num: int):
        """
        Process a chunk in background thread.

        FAIL-SAFE: This will NEVER crash or affect recording.
        Any errors are caught and logged, but recording continues.
        """
        if self.on_chunk_ready:
            try:
                self.on_chunk_ready(chunk_path, chunk_num)
            except Exception as e:
                # Log error but NEVER crash - recording must continue
                try:
                    print(f"\n  [Warning] Error processing chunk {chunk_num}: {e}")
                    print(f"  [Warning] Audio saved to: {chunk_path}")
                    print(f"  [Warning] You can reprocess later with: ./run.sh transcribe {chunk_path}")
                except:
                    pass  # Even print failures shouldn't crash

    def _setup_terminal(self):
        """Set terminal to raw mode for single keypress detection."""
        self._original_term_settings = termios.tcgetattr(sys.stdin)
        tty.setraw(sys.stdin.fileno())

    def _restore_terminal(self):
        """Restore terminal to original settings."""
        if self._original_term_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._original_term_settings)

    def _read_key(self) -> str:
        """Read a single keypress."""
        return sys.stdin.read(1)

    def run(self):
        """Main recording loop. Press SPACE to cut chunk, Q or Ctrl+C to quit."""
        self.running = True

        print(f"\n{'='*60}")
        print("INTERACTIVE RECORDING")
        print(f"{'='*60}")
        print(f"Session: {self.session_id}")
        print(f"Output:  {self.session_dir}")
        print(f"{'='*60}")
        print("\nControls:")
        print("  SPACE  - Cut chunk (saves current, starts new)")
        print("  Q      - Quit recording")
        print(f"{'='*60}\n")

        # Start first recording
        self._start_recording()
        print(f"🔴 Recording chunk {self.chunk_number}... (press SPACE to cut)")

        try:
            self._setup_terminal()

            while self.running:
                key = self._read_key()

                if key == ' ':
                    # Spacebar: cut current chunk, start new one immediately
                    current_chunk_num = self.chunk_number
                    chunk_path = self._stop_recording()

                    # Immediately start new recording (minimal gap)
                    self._start_recording()

                    # Restore terminal briefly to print status
                    self._restore_terminal()
                    print(f"\n✂️  Chunk {current_chunk_num} saved ({chunk_path.name if chunk_path else 'empty'})")
                    print(f"🔴 Recording chunk {self.chunk_number}... (press SPACE to cut)")
                    self._setup_terminal()

                    # Process the saved chunk in background
                    if chunk_path:
                        thread = threading.Thread(
                            target=self._process_chunk_background,
                            args=(chunk_path, current_chunk_num),
                            daemon=True
                        )
                        thread.start()

                elif key.lower() == 'q' or ord(key) == 3:  # Q or Ctrl+C
                    self.running = False

        except Exception as e:
            print(f"\nError: {e}")
        finally:
            self._restore_terminal()

            # Stop final recording
            final_chunk = self._stop_recording()
            if final_chunk:
                print(f"\n✂️  Final chunk {self.chunk_number - 1} saved")
                # Process final chunk
                if self.on_chunk_ready:
                    self._process_chunk_background(final_chunk, self.chunk_number - 1)

            print(f"\n{'='*60}")
            print("SESSION COMPLETE")
            print(f"{'='*60}")
            print(f"Chunks recorded: {self.chunk_number}")
            print(f"Audio directory: {self.session_dir}")
            print(f"{'='*60}\n")

        return self.session_dir


def test_interactive():
    """Test interactive recording without processing."""
    def on_chunk(path, num):
        print(f"  [Background] Would process: {path}")

    recorder = InteractiveRecorder(on_chunk_ready=on_chunk)
    recorder.run()


if __name__ == "__main__":
    test_interactive()
