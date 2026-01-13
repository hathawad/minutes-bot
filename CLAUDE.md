# Claude Code Setup Instructions

When a user asks to "install", "set up", or "get started" with this project, follow these steps:

## 1. Check Prerequisites

Verify these are installed (prompt user to install if missing):

```bash
# Check for Homebrew
which brew || echo "Install Homebrew from https://brew.sh"

# Check for Python 3
python3 --version || echo "Install Python 3"
```

## 2. Install System Dependencies

```bash
# Audio recording
brew install sox

# Local transcription (whisper-cpp)
brew install whisper-cpp
```

## 3. Download Whisper Model

```bash
mkdir -p ~/.cache/whisper-cpp
curl -L -o ~/.cache/whisper-cpp/ggml-small.en.bin \
  "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"
```

Other model options (trade-off: size vs accuracy):
- `ggml-tiny.en.bin` (75 MB) - fastest, least accurate
- `ggml-base.en.bin` (142 MB) - fast, decent accuracy
- `ggml-small.en.bin` (466 MB) - recommended balance
- `ggml-medium.en.bin` (1.5 GB) - slower, more accurate
- `ggml-large.bin` (2.9 GB) - slowest, most accurate

## 4. Set Up Python Environment

```bash
cd /path/to/minutes-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 5. Configure API Key

Ask the user for their Anthropic API key, then:

```bash
echo 'ANTHROPIC_API_KEY=their-key-here' > .env
```

If they don't have one, the bot still works for recording and transcription (offline mode).
They can get a key at: https://console.anthropic.com/

## 6. Test the Installation

```bash
# Test microphone access
./run.sh test-mic

# Should see: "Recording 3 seconds... Done!"
```

If microphone test fails, the user may need to grant Terminal/IDE microphone permissions in:
**System Preferences → Privacy & Security → Microphone**

## 7. Quick Start

```bash
# Start recording a meeting (interactive mode with UI)
./run.sh start "Meeting Name"

# Controls: SPACE to cut chunks, Q to quit
```

## Troubleshooting

- **"sox: command not found"** → Run `brew install sox`
- **"whisper-cli: command not found"** → Run `brew install whisper-cpp`
- **"Model not found"** → Download model (step 3)
- **Empty transcripts** → Check microphone permissions, increase system input volume
- **"ANTHROPIC_API_KEY not set"** → Create .env file (step 5) or export the variable
