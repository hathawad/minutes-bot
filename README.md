# Minutes Bot

A better way to take meeting minutes for any board, especially non-profits.

![Minutes Bot UI](docs/screenshot.png)

## What It Does

Minutes Bot records your meeting, transcribes it locally, and generates formatted meeting minutes automatically. It's designed for board secretaries who spend hours writing minutes after every meeting.

**Key Features:**
- **Interactive recording** with real-time audio level display
- **Local transcription** using Whisper (works offline)
- **AI-powered minutes** via Claude API (queues when offline)
- **Agenda-aware** - organizes minutes around your agenda topics
- **Style matching** - learns from your previous minutes format
- **Wall clock timestamps** - tracks when each section started
- **Fault-tolerant** - never loses audio, even if something crashes

## Quick Setup with Claude Code

If you have [Claude Code](https://claude.ai/code) installed, just say:

> "set up the project"

Claude will install all dependencies, download models, and configure everything.

## Manual Setup

**Requirements:** macOS (Intel or Apple Silicon)

```bash
# Install dependencies
brew install sox whisper-cpp

# Download Whisper model
mkdir -p ~/.cache/whisper-cpp
curl -L -o ~/.cache/whisper-cpp/ggml-small.en.bin \
  "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"

# Set up Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure API key
echo 'ANTHROPIC_API_KEY=your-key-here' > .env
```

## Usage

```bash
# Start recording (interactive mode with UI)
./run.sh start "Board Meeting"

# Controls: SPACE to cut chunks, Q to quit
```

### Preparing for a Meeting

1. **Add your agenda** to `agendas/` (supports .docx, .md, .txt)
2. **Add sample minutes** to `samples/` for style reference
3. Run the bot - it will organize output around your agenda and match your format

### Other Commands

```bash
./run.sh test-mic                    # Test microphone
./run.sh start "Meeting" --basic     # Text-only mode (no UI)
./run.sh record "Meeting"            # Auto-chunk every 5 minutes
./run.sh transcribe audio.wav        # Transcribe a file
./run.sh process-queue               # Process offline queue
```

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   SoX       │────▶│   Whisper   │────▶│  Claude API │
│  (record)   │     │ (transcribe)│     │  (minutes)  │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
   audio/             transcripts/          minutes/
   + backup           + timestamps         + agenda sections
                                           + timing info
```

1. **Record** - Press SPACE to mark section boundaries (topic changes)
2. **Transcribe** - Whisper converts audio to text with timestamps
3. **Generate** - Claude creates minutes matching your style and agenda

## Output Format

Minutes include wall clock timestamps for each section:

```markdown
## 2. Opening (7:30 PM)
- **Prayer:** John Smith

## 3. Old Business (7:35 PM)
### A. Budget Review
- Q4 financials approved unanimously
...

## 7. Closing (8:45 PM)
- **Adjournment:** 8:45 PM
```

## Files Generated

```
data/
  audio/{session}/
    chunk_0000.wav              # Audio segments
    full_session_backup.wav     # Complete recording
  transcripts/{session}/
    chunk_0000.txt              # Timestamped segments
    full_transcript.txt         # Combined transcript
  minutes/
    {session}_{meeting}.md      # Final minutes
```

## Offline Support

**Recording never stops due to network issues.** The system is fault-tolerant:

- Audio is always saved locally first
- Transcription runs locally (no internet needed)
- If Claude API fails, transcripts queue for later
- Run `./run.sh process-queue` when back online

## Configuration

Edit `config.py` to customize:
- `WHISPER_MODEL`: tiny, base, small, medium, large
- `CHUNK_DURATION_SECONDS`: Auto-chunk interval (default: 300)
- `DEFAULT_TEMPLATE`: Minutes template format

## License

MIT
