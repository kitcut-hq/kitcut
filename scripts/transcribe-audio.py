#!/usr/bin/env python3
"""
Transcribe audio file to text with word-level timestamps.

Uses OpenAI Whisper API for accurate speech-to-text with word-level precision.
This is useful for syncing voiceovers to video frames.

Usage:
    python transcribe-audio.py audio/Recording.m4a > script.json
    python transcribe-audio.py audio/Recording.m4a --model large-v3
"""

import sys
import json
import os
import argparse
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


def load_env():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        print(f"Warning: {env_file} not found. Set OPENAI_API_KEY manually.", file=sys.stderr)
        return {}

    env_vars = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()
    return env_vars


def transcribe_audio(file_path, model="whisper-1", language=None):
    """
    Transcribe audio file using OpenAI Whisper API.

    Args:
        file_path: Path to audio file (.mp3, .m4a, .wav, .flac, .ogg)
        model: Whisper model (always "whisper-1" for API)
        language: ISO-639-1 language code (e.g., "en", "uk", "fr")

    Returns:
        dict with transcript and word-level timestamps
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        env_vars = load_env()
        api_key = env_vars.get("OPENAI_API_KEY")

    if not api_key:
        print("Error: OPENAI_API_KEY not set. Add to .env or export as environment variable.", file=sys.stderr)
        sys.exit(1)

    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Transcribing: {file_path}", file=sys.stderr)
    print(f"Model: {model}", file=sys.stderr)

    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}

    params = {
        "model": model,
        "response_format": "verbose_json",
        "timestamp_granularities[]": "word"
    }

    if language:
        params["language"] = language

    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f, "audio/mpeg")}
        response = requests.post(url, headers=headers, files=files, data=params)

    if response.status_code != 200:
        print(f"Error: {response.status_code}", file=sys.stderr)
        print(response.text, file=sys.stderr)
        sys.exit(1)

    return response.json()


def format_output(transcript_data, include_raw=False):
    """Format transcript for easy reading."""
    result = {
        "file": transcript_data.get("text", ""),
        "duration": transcript_data.get("duration"),
        "language": transcript_data.get("language", "unknown"),
        "words": []
    }

    if "words" in transcript_data:
        for word in transcript_data["words"]:
            result["words"].append({
                "text": word["word"],
                "start": round(word["start"], 3),
                "end": round(word["end"], 3),
                "duration": round(word["end"] - word["start"], 3)
            })

    if include_raw:
        result["_raw"] = transcript_data

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio with word-level timestamps using OpenAI Whisper"
    )
    parser.add_argument("file", help="Audio file path (.m4a, .mp3, .wav, .flac, .ogg)")
    parser.add_argument("--model", default="whisper-1", help="Whisper model (default: whisper-1)")
    parser.add_argument("--language", help="Language code (e.g., en, uk, fr)")
    parser.add_argument("--output", help="Save to file instead of stdout")
    parser.add_argument("--include-raw", action="store_true", help="Include raw API response")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    args = parser.parse_args()

    # Transcribe
    transcript = transcribe_audio(args.file, model=args.model, language=args.language)

    # Format
    result = format_output(transcript, include_raw=args.include_raw)

    # Output
    if args.pretty:
        output_json = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        output_json = json.dumps(result, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"Saved to: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
