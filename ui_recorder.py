"""Interactive recorder with real-time audio level display."""

import subprocess
import sys
import threading
import time
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn
from rich.table import Table
from rich.text import Text
from rich import box

import config


class AudioLevelMonitor:
    """Monitors audio input levels in real-time."""

    def __init__(self):
        self.level = 0.0
        self.peak = 0.0
        self.running = False
        self._stream = None

    def _audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice for each audio block."""
        # Calculate RMS level
        rms = np.sqrt(np.mean(indata**2))
        self.level = min(rms * 10, 1.0)  # Scale and cap at 1.0
        self.peak = max(self.peak, self.level)
        # Decay peak slowly
        self.peak = max(self.peak * 0.95, self.level)

    def start(self):
        """Start monitoring audio levels."""
        if not SOUNDDEVICE_AVAILABLE:
            return

        try:
            self._stream = sd.InputStream(
                channels=1,
                samplerate=config.SAMPLE_RATE,
                callback=self._audio_callback,
                blocksize=1024
            )
            self._stream.start()
            self.running = True
        except Exception as e:
            print(f"Could not start audio monitor: {e}")

    def stop(self):
        """Stop monitoring audio levels."""
        self.running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class UIRecorder:
    """Interactive recorder with rich terminal UI."""

    def __init__(self, on_chunk_ready: Optional[Callable[[Path, int], None]] = None):
        self.on_chunk_ready = on_chunk_ready
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = config.AUDIO_DIR / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.chunk_number = 0
        self.recording_process: Optional[subprocess.Popen] = None
        self.backup_process: Optional[subprocess.Popen] = None
        self.backup_file: Optional[Path] = None
        self.running = False
        self._processing_threads: list[threading.Thread] = []
        self._pending_chunks = 0
        self._completed_chunks = 0
        self._last_transcript = ""
        self._status_message = ""

        self.console = Console()
        self.level_monitor = AudioLevelMonitor()

    def _get_chunk_path(self) -> Path:
        return self.session_dir / f"chunk_{self.chunk_number:04d}.wav"

    def _start_backup_recording(self):
        self.backup_file = self.session_dir / "full_session_backup.wav"
        cmd = [
            "sox", "-d", "-c", str(config.CHANNELS),
            "-r", str(config.SAMPLE_RATE), "-b", "16",
            str(self.backup_file),
        ]
        self.backup_process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def _stop_backup_recording(self):
        if self.backup_process:
            self.backup_process.terminate()
            try:
                self.backup_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.backup_process.kill()
            self.backup_process = None

    def _start_recording(self) -> Path:
        output_path = self._get_chunk_path()
        cmd = [
            "sox", "-d", "-c", str(config.CHANNELS),
            "-r", str(config.SAMPLE_RATE), "-b", "16",
            str(output_path),
        ]
        self.recording_process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return output_path

    def _stop_recording(self) -> Optional[Path]:
        if self.recording_process is None:
            return None

        current_path = self._get_chunk_path()
        self.recording_process.terminate()
        try:
            self.recording_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.recording_process.kill()
            self.recording_process.wait()

        self.recording_process = None
        self.chunk_number += 1

        if current_path.exists() and current_path.stat().st_size > 1000:
            return current_path
        return None

    def _process_chunk_background(self, chunk_path: Path, chunk_num: int):
        self._pending_chunks += 1
        try:
            if self.on_chunk_ready:
                self.on_chunk_ready(chunk_path, chunk_num)
            self._completed_chunks += 1
        except Exception as e:
            self._status_message = f"Error on chunk {chunk_num}: {str(e)[:30]}"
        finally:
            self._pending_chunks -= 1

    def _build_display(self) -> Panel:
        """Build the rich display panel."""
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Label", style="bold cyan", width=12)
        table.add_column("Value", width=50)

        # Session info
        table.add_row("Session", self.session_id)
        table.add_row("Chunk", f"{self.chunk_number}")

        # Audio level bar
        level = self.level_monitor.level
        peak = self.level_monitor.peak
        bar_width = 40
        level_bars = int(level * bar_width)
        peak_pos = int(peak * bar_width)

        # Build level bar with colors
        bar_chars = []
        for i in range(bar_width):
            if i < level_bars:
                if i < bar_width * 0.6:
                    bar_chars.append("[green]█[/green]")
                elif i < bar_width * 0.8:
                    bar_chars.append("[yellow]█[/yellow]")
                else:
                    bar_chars.append("[red]█[/red]")
            elif i == peak_pos and peak > 0.01:
                bar_chars.append("[white]│[/white]")
            else:
                bar_chars.append("[dim]░[/dim]")

        level_bar = "".join(bar_chars)
        table.add_row("Level", Text.from_markup(level_bar))

        # Processing status
        if self._pending_chunks > 0:
            status = f"[yellow]Processing {self._pending_chunks} chunk(s)...[/yellow]"
        else:
            status = "[green]Ready[/green]"
        table.add_row("Status", Text.from_markup(status))

        # Last transcript preview
        if self._last_transcript:
            preview = self._last_transcript[:45] + "..." if len(self._last_transcript) > 45 else self._last_transcript
            table.add_row("Last", preview)

        # Controls
        controls = Text()
        controls.append("SPACE", style="bold white on blue")
        controls.append(" Cut chunk  ", style="dim")
        controls.append("Q", style="bold white on red")
        controls.append(" Quit", style="dim")

        # Main panel
        content = Table.grid(padding=1)
        content.add_row(table)
        content.add_row(controls)

        return Panel(
            content,
            title="[bold red]● REC[/bold red] MINUTE BOT",
            border_style="red",
            box=box.ROUNDED
        )

    def run(self, meeting_name: str = "Meeting"):
        """Main recording loop with UI."""
        self.running = True

        # Start backup and first chunk
        self._start_backup_recording()
        self._start_recording()
        self.level_monitor.start()

        # Set up keyboard input
        import tty
        import termios
        old_settings = termios.tcgetattr(sys.stdin)

        try:
            tty.setcbreak(sys.stdin.fileno())  # Use cbreak instead of raw for better compat

            with Live(self._build_display(), console=self.console, refresh_per_second=15) as live:
                while self.running:
                    live.update(self._build_display())

                    # Non-blocking key check
                    import select
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        key = sys.stdin.read(1)

                        if key == ' ':
                            # Cut chunk
                            current_chunk_num = self.chunk_number
                            chunk_path = self._stop_recording()
                            self._start_recording()

                            if chunk_path:
                                thread = threading.Thread(
                                    target=self._process_chunk_background,
                                    args=(chunk_path, current_chunk_num),
                                    daemon=False
                                )
                                thread.start()
                                self._processing_threads.append(thread)

                        elif key.lower() == 'q' or ord(key) == 3:
                            self.running = False

        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            self.level_monitor.stop()

            # Stop final recording
            final_chunk = self._stop_recording()
            if final_chunk and self.on_chunk_ready:
                self._process_chunk_background(final_chunk, self.chunk_number - 1)

            self._stop_backup_recording()

            # Wait for pending threads
            pending = [t for t in self._processing_threads if t.is_alive()]
            if pending:
                self.console.print(f"\n[yellow]Waiting for {len(pending)} chunk(s)...[/yellow]")
                for t in pending:
                    t.join(timeout=120)

            # Final summary
            backup_size = ""
            if self.backup_file and self.backup_file.exists():
                size_mb = self.backup_file.stat().st_size / (1024 * 1024)
                backup_size = f"({size_mb:.1f} MB)"

            self.console.print(Panel(
                f"[bold]Chunks:[/bold] {self.chunk_number}\n"
                f"[bold]Directory:[/bold] {self.session_dir}\n"
                f"[bold]Backup:[/bold] {self.backup_file.name} {backup_size}",
                title="[bold green]SESSION COMPLETE[/bold green]",
                border_style="green"
            ))

        return self.session_dir


def test_ui():
    """Test the UI recorder."""
    def on_chunk(path, num):
        time.sleep(2)  # Simulate processing
        print(f"Processed: {path}")

    recorder = UIRecorder(on_chunk_ready=on_chunk)
    recorder.run("Test Meeting")


if __name__ == "__main__":
    test_ui()
