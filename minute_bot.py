#!/usr/bin/env python3
"""
Minute Bot - Automated meeting minutes generation

Records audio in chunks, transcribes locally with Whisper,
and generates/updates minutes using Claude API.

Usage:
    python minute_bot.py start "Board Meeting"     # Interactive (spacebar to cut)
    python minute_bot.py record "Board Meeting"    # Timed chunks
    python minute_bot.py test-mic
    python minute_bot.py transcribe /path/to/audio.wav
"""

import argparse
import sys
from datetime import datetime

import config
from recorder import AudioRecorder, test_microphone
from transcriber import Transcriber, TranscriptManager
from minutes_generator import MinutesGenerator, OfflineMinutesStore
from interactive_recorder import InteractiveRecorder

try:
    from ui_recorder import UIRecorder
    UI_AVAILABLE = True
except ImportError:
    UI_AVAILABLE = False


def ui_meeting(meeting_name: str, model: str):
    """Interactive recording with rich UI and audio level meter."""
    if not UI_AVAILABLE:
        print("UI dependencies not available. Install with: pip install sounddevice rich")
        print("Falling back to basic interactive mode.\n")
        interactive_meeting(meeting_name, model)
        return

    if not config.ANTHROPIC_API_KEY:
        print("Warning: ANTHROPIC_API_KEY not set. Running in offline mode.\n")

    transcriber = Transcriber(model=model)
    transcript_mgr = None
    minutes_gen = None
    offline_store = None

    def on_chunk_ready(audio_path, chunk_number, chunk_start):
        nonlocal transcript_mgr, minutes_gen, offline_store

        if transcript_mgr is None:
            session_id = audio_path.parent.name
            transcript_mgr = TranscriptManager(session_id)
            minutes_gen = MinutesGenerator(meeting_name, session_id=session_id)
            offline_store = OfflineMinutesStore(session_id)
            minutes_gen.offline_queue = offline_store.load_queue()

        result = transcriber.transcribe(audio_path, chunk_start_time=chunk_start)
        text = result.get("text", "").strip()
        timestamped = result.get("timestamped_text", "").strip()

        if not text:
            return

        # Use timestamped text for transcript, plain text for minutes
        transcript_mgr.append(timestamped if timestamped else text, chunk_number)
        minutes_gen.update_minutes(text, chunk_number)
        offline_store.save_queue(minutes_gen.offline_queue)

    recorder = UIRecorder(on_chunk_ready=on_chunk_ready)
    recorder.run(meeting_name)

    # Finalize minutes with end time
    if minutes_gen:
        minutes_gen.finalize()
        print(f"\n📋 Minutes: {minutes_gen.minutes_file}")
    if transcript_mgr:
        print(f"📝 Transcript: {transcript_mgr.transcript_file}")


def interactive_meeting(meeting_name: str, model: str):
    """Interactive recording with spacebar-triggered chunks (basic mode)."""

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                      MINUTE BOT                              ║
║            Interactive Meeting Minutes                       ║
╠══════════════════════════════════════════════════════════════╣
║  Meeting: {meeting_name:<50} ║
║  Whisper model: {model:<44} ║
║  Mode: SPACEBAR to cut chunks                                ║
╚══════════════════════════════════════════════════════════════╝
""")

    if not config.ANTHROPIC_API_KEY:
        print("Warning: ANTHROPIC_API_KEY not set. Running in offline mode.\n")

    # These will be initialized once we have a session ID
    transcriber = Transcriber(model=model)
    transcript_mgr = None
    minutes_gen = None
    offline_store = None

    def on_chunk_ready(audio_path, chunk_number, chunk_start):
        """Process a chunk in the background."""
        nonlocal transcript_mgr, minutes_gen, offline_store

        # Initialize on first chunk (now we have session ID from path)
        if transcript_mgr is None:
            session_id = audio_path.parent.name
            transcript_mgr = TranscriptManager(session_id)
            minutes_gen = MinutesGenerator(meeting_name, session_id=session_id)
            offline_store = OfflineMinutesStore(session_id)
            minutes_gen.offline_queue = offline_store.load_queue()

        print(f"\n  📝 Processing chunk {chunk_number}...")

        # Transcribe with wall clock timestamps
        result = transcriber.transcribe(audio_path, chunk_start_time=chunk_start)
        text = result.get("text", "").strip()
        timestamped = result.get("timestamped_text", "").strip()

        if not text:
            print(f"  ⚪ Chunk {chunk_number}: (no speech detected)")
            return

        print(f"  📜 Transcript: {text[:80]}{'...' if len(text) > 80 else ''}")

        # Save transcript with timestamps
        transcript_mgr.append(timestamped if timestamped else text, chunk_number)

        # Update minutes
        success = minutes_gen.update_minutes(text, chunk_number)
        if success:
            print(f"  ✅ Minutes updated")
        else:
            print(f"  📦 Queued for later (offline)")

        # Persist queue
        offline_store.save_queue(minutes_gen.offline_queue)

    # Run interactive recorder
    recorder = InteractiveRecorder(on_chunk_ready=on_chunk_ready)

    try:
        session_dir = recorder.run()
    finally:
        # Finalize minutes with end time
        if minutes_gen:
            minutes_gen.finalize()
            print(f"\n📋 Minutes saved to: {minutes_gen.minutes_file}")
        if transcript_mgr:
            print(f"📝 Full transcript: {transcript_mgr.transcript_file}")


def record_meeting(meeting_name: str, chunk_duration: int, model: str):
    """Main recording loop with transcription and minutes generation."""

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                      MINUTE BOT                              ║
║            Automated Meeting Minutes                         ║
╠══════════════════════════════════════════════════════════════╣
║  Meeting: {meeting_name:<50} ║
║  Chunk duration: {chunk_duration}s                                        ║
║  Whisper model: {model:<44} ║
║  Offline capable: Yes (transcripts queued when offline)     ║
╠══════════════════════════════════════════════════════════════╣
║  Press Ctrl+C to stop recording                              ║
╚══════════════════════════════════════════════════════════════╝
""")

    # Initialize components
    recorder = AudioRecorder(chunk_duration=chunk_duration)
    transcriber = Transcriber(model=model)
    transcript_mgr = TranscriptManager(recorder.session_id)
    minutes_gen = MinutesGenerator(meeting_name, session_id=recorder.session_id)
    offline_store = OfflineMinutesStore(recorder.session_id)

    # Load any previously queued transcripts
    minutes_gen.offline_queue = offline_store.load_queue()
    if minutes_gen.offline_queue:
        print(f"Loaded {len(minutes_gen.offline_queue)} queued transcripts from previous session")

    def process_chunk(audio_path):
        """Callback for each recorded chunk."""
        print(f"\n{'='*60}")
        print(f"Processing chunk: {audio_path.name}")
        print(f"{'='*60}")

        # Transcribe
        result = transcriber.transcribe(audio_path)
        text = result.get("text", "").strip()

        if not text:
            print("  (No speech detected)")
            return

        # Save transcript
        transcript_mgr.append(text, recorder.chunk_number - 1)

        # Update minutes
        minutes_gen.update_minutes(text, recorder.chunk_number - 1)

        # Try to process queue if we have connectivity
        if minutes_gen.offline_queue:
            minutes_gen.process_queue()

        # Persist queue in case of crash
        offline_store.save_queue(minutes_gen.offline_queue)

        print(f"\nWaiting for next chunk...")

    try:
        recorder.start_continuous(callback=process_chunk)
    except KeyboardInterrupt:
        pass
    finally:
        # Finalize minutes with end time
        minutes_gen.finalize()
        offline_store.save_queue(minutes_gen.offline_queue)

        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    SESSION COMPLETE                          ║
╠══════════════════════════════════════════════════════════════╣
║  Chunks recorded: {recorder.chunk_number:<42} ║
║  Audio files: {str(recorder.session_dir):<46} ║
║  Transcript: {str(transcript_mgr.transcript_file):<47} ║
║  Minutes: {str(minutes_gen.minutes_file):<50} ║
║  Queued (offline): {len(minutes_gen.offline_queue):<41} ║
╚══════════════════════════════════════════════════════════════╝
""")


def transcribe_file(audio_path: str, model: str):
    """Transcribe a single audio file."""
    from pathlib import Path
    path = Path(audio_path)
    if not path.exists():
        print(f"File not found: {audio_path}")
        sys.exit(1)

    transcriber = Transcriber(model=model)
    result = transcriber.transcribe(path)
    print(f"\nTranscription:\n{result.get('text', 'No text')}")


def process_offline_queue():
    """Find and process any queued transcripts from offline sessions."""
    import json

    queue_files = list(config.DATA_DIR.glob("*_offline_queue.json"))

    if not queue_files:
        print("No offline queues found.")
        return

    print(f"Found {len(queue_files)} offline queue(s):\n")

    for queue_file in queue_files:
        session_id = queue_file.stem.replace("_offline_queue", "")
        print(f"Session: {session_id}")

        try:
            with open(queue_file) as f:
                queue = json.load(f)

            if not queue:
                print("  (empty queue)")
                continue

            print(f"  Queued chunks: {len(queue)}")

            # Combine all transcripts
            combined_text = "\n\n".join(
                f"[Chunk {item.get('chunk', '?')}]\n{item.get('text', '')}"
                for item in queue
            )

            # Try to find the meeting name from existing minutes
            minutes_files = list(config.MINUTES_DIR.glob(f"{session_id}*.md"))
            if minutes_files:
                meeting_name = minutes_files[0].stem.split("_", 2)[-1] if "_" in minutes_files[0].stem else "Meeting"
            else:
                meeting_name = "Meeting"

            print(f"  Meeting: {meeting_name}")
            print(f"  Processing...")

            # Create generator and process
            gen = MinutesGenerator(meeting_name)
            if minutes_files and minutes_files[0].exists():
                gen.current_minutes = minutes_files[0].read_text()
                gen.minutes_file = minutes_files[0]

            success = gen.update_minutes(combined_text, -1)

            if success:
                print(f"  ✅ Minutes updated: {gen.minutes_file}")
                # Clear the queue file
                queue_file.unlink()
                print(f"  ✅ Queue cleared")
            else:
                print(f"  ❌ Failed to process (still offline?)")

        except Exception as e:
            print(f"  ❌ Error: {e}")

        print()


def main():
    parser = argparse.ArgumentParser(
        description="Minute Bot - Automated meeting minutes generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s start "Board Meeting"                    # Interactive (SPACE to cut)
  %(prog)s record "HOA Meeting" --chunk-duration 180  # Timed chunks
  %(prog)s test-mic
  %(prog)s transcribe recording.wav
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Start command (interactive, spacebar-triggered)
    start_parser = subparsers.add_parser("start", help="Start interactive recording (SPACE to cut chunks)")
    start_parser.add_argument("meeting_name", help="Name of the meeting")
    start_parser.add_argument(
        "--model", "-m",
        default=config.WHISPER_MODEL,
        choices=["tiny", "base", "small", "medium", "large"],
        help=f"Whisper model to use (default: {config.WHISPER_MODEL})"
    )
    start_parser.add_argument(
        "--basic", "-b",
        action="store_true",
        help="Use basic mode without UI (no audio level meter)"
    )

    # Record command (timed chunks)
    record_parser = subparsers.add_parser("record", help="Record with timed chunks (auto-cut every N seconds)")
    record_parser.add_argument("meeting_name", help="Name of the meeting")
    record_parser.add_argument(
        "--chunk-duration", "-c",
        type=int,
        default=config.CHUNK_DURATION_SECONDS,
        help=f"Duration of each chunk in seconds (default: {config.CHUNK_DURATION_SECONDS})"
    )
    record_parser.add_argument(
        "--model", "-m",
        default=config.WHISPER_MODEL,
        choices=["tiny", "base", "small", "medium", "large"],
        help=f"Whisper model to use (default: {config.WHISPER_MODEL})"
    )

    # Test mic command
    subparsers.add_parser("test-mic", help="Test microphone recording")

    # Transcribe command
    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe an audio file")
    transcribe_parser.add_argument("audio_file", help="Path to audio file")
    transcribe_parser.add_argument(
        "--model", "-m",
        default=config.WHISPER_MODEL,
        help=f"Whisper model (default: {config.WHISPER_MODEL})"
    )

    # Process queue command
    subparsers.add_parser("process-queue", help="Process queued transcripts from offline sessions")

    args = parser.parse_args()

    if args.command == "start":
        if args.basic:
            interactive_meeting(args.meeting_name, args.model)
        else:
            ui_meeting(args.meeting_name, args.model)

    elif args.command == "record":
        if not config.ANTHROPIC_API_KEY:
            print("Warning: ANTHROPIC_API_KEY not set. Running in offline mode.")
            print("Minutes will be generated when API key is available.\n")
        record_meeting(args.meeting_name, args.chunk_duration, args.model)

    elif args.command == "test-mic":
        test_microphone()

    elif args.command == "transcribe":
        transcribe_file(args.audio_file, args.model)

    elif args.command == "process-queue":
        process_offline_queue()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
