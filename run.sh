#!/bin/bash
# Convenience wrapper for minute-bot
cd "$(dirname "$0")"

# Load .env if it exists
[ -f .env ] && export $(grep -v '^#' .env | xargs)

source .venv/bin/activate
python minute_bot.py "$@"
