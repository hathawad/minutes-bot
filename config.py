"""Configuration for the meeting minutes bot."""

import os
from pathlib import Path

# Directories
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
MINUTES_DIR = DATA_DIR / "minutes"
TEMPLATES_DIR = BASE_DIR / "templates"

# Create directories
for d in [DATA_DIR, AUDIO_DIR, TRANSCRIPTS_DIR, MINUTES_DIR, TEMPLATES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Audio settings
SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHANNELS = 1  # Mono
CHUNK_DURATION_SECONDS = 300  # 5 minutes default

# Whisper settings
WHISPER_MODEL = "small"  # Options: tiny, base, small, medium, large
WHISPER_LANGUAGE = "en"

# Claude API
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Default minutes template
DEFAULT_TEMPLATE = """
# Meeting Minutes

**Date:** {date}
**Meeting:** {meeting_name}
**Started:** {start_time}
**Ended:** {end_time}

## Attendees
- (To be filled based on transcript)

## Agenda Items

## Discussion Summary

## Action Items

## Next Steps
"""
