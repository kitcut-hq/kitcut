#!/usr/bin/env python3
"""
Generate TTS voiceover with background music ducking.

Uses ElevenLabs for text-to-speech and FFmpeg for music mixing with sidechain compression.
Creates a professional voiceover track that ducks background music when speaking.

Usage:
    python generate-voiceover.py \\
      --script scripts/hpd-omo-script.txt \\
      --output temp/voiceover.wav \\
      --background-music audio/background.mp3

Script format (JSON):
    [
      {"time": 1.60, "text": "First line of narration..."},
      {"time": 9.10, "text": "Second line..."},
      ...
    ]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402 -- re-execs into .venv; before any 3rd-party import
import json
import os
import argparse
import subprocess
import tempfile
from pathlib import Path
from time import time as now


try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


def load_env():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent.parent / ".env"
    env_vars = {}
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    env_vars[key.strip()] = val.strip()
    return env_vars


def get_elevenlabs_key():
    """Get ElevenLabs API key from environment."""
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        env_vars = load_env()
        key = env_vars.get("ELEVENLABS_API_KEY")
    if not key:
        print("Error: ELEVENLABS_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    return key


def load_script(script_file):
    """Load voiceover script from JSON file."""
    if script_file.endswith(".json"):
        with open(script_file) as f:
            return json.load(f)

    # Alternative: simple text format with timestamps
    lines = []
    with open(script_file) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line and not line.startswith("#"):
                # Format: "time|text" or just "text" (auto-number)
                if "|" in line:
                    time_str, text = line.split("|", 1)
                    time = float(time_str)
                else:
                    time = line_num * 5  # Simple spacing
                    text = line
                lines.append({"time": time, "text": text})
    return lines


def generate_speech(text, voice_id, api_key, model="eleven_turbo_v2_5"):
    """
    Generate speech using ElevenLabs TTS API.

    Returns: bytes of audio data (16kHz, mono, PCM)
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": api_key}

    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"Error: ElevenLabs API returned {response.status_code}", file=sys.stderr)
        print(response.text, file=sys.stderr)
        sys.exit(1)

    return response.content


def estimate_duration(text):
    """Rough estimate of speech duration (words * 0.6 seconds)."""
    word_count = len(text.split())
    return word_count * 0.6


def create_timed_voiceover(script_lines, voice_id, api_key, model):
    """
    Generate individual clips at scheduled times, create timing file for FFmpeg.

    Returns: (audio_file, timing_list)
    """
    api_key = get_elevenlabs_key()
    clips = []
    timing_map = []  # For FFmpeg atrim/adelay

    with tempfile.TemporaryDirectory() as tmpdir:
        for idx, line in enumerate(script_lines, 1):
            start_time = line["time"]
            text = line["text"]

            print(f"[{idx}/{len(script_lines)}] Generating: {text[:50]}...", file=sys.stderr)
            print(f"  Start: {start_time:.2f}s", file=sys.stderr)

            # Generate TTS
            audio_data = generate_speech(text, voice_id, api_key, model)

            # Save clip
            clip_file = Path(tmpdir) / f"clip_{idx:02d}.wav"
            with open(clip_file, "wb") as f:
                f.write(audio_data)

            estimated_duration = estimate_duration(text)
            clips.append({
                "idx": idx,
                "file": str(clip_file),
                "start": start_time,
                "text": text,
                "estimated_duration": estimated_duration
            })

            print(f"  Estimated duration: {estimated_duration:.2f}s", file=sys.stderr)
            print()

        # Build FFmpeg concat file
        concat_file = Path(tmpdir) / "concat.txt"
        with open(concat_file, "w") as f:
            for clip in clips:
                f.write(f"file '{clip['file']}'\n")

        # Concatenate all clips
        output_wav = Path(tmpdir) / "voiceover_raw.wav"
        cmd = [
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "pcm_s16le",
            str(output_wav)
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        print(f"Generated voiceover: {output_wav}", file=sys.stderr)

        return str(output_wav), clips


def mix_with_music(voiceover_file, music_file, output_file):
    """
    Mix voiceover with background music using sidechain compression.
    """
    cmd = [
        "ffmpeg",
        "-i", voiceover_file,
        "-i", music_file,
        "-filter_complex",
        (
            "[0]volume=+7.04dB,asplit=2[vo1][sc];"
            "[1]aformat=channel_layouts=stereo[mus];"
            "[sc]aformat=channel_layouts=stereo[scs];"
            "[mus][scs]sidechaincompress=threshold=0.035:ratio=9:attack=12:release=380:makeup=1[duck];"
            "[vo1]aformat=channel_layouts=stereo[vos];"
            "[duck][vos]amix=inputs=2:normalize=0:dropout_transition=0[pre];"
            "[pre]alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
        ),
        "-map", "[aout]",
        "-b:a", "128k",
        "-ac", "2",
        output_file
    ]

    print(f"Mixing with background music...", file=sys.stderr)
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"Output: {output_file}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Generate TTS voiceover with background music ducking"
    )
    parser.add_argument("--script", required=True, help="Script file (JSON or text)")
    parser.add_argument("--output", required=True, help="Output audio file")
    parser.add_argument("--background-music", help="Background music file")
    parser.add_argument("--voice", default="nPczCjzI2devNBz1zQrb", help="ElevenLabs voice ID")
    parser.add_argument("--model", default="eleven_turbo_v2_5", help="TTS model")
    parser.add_argument("--no-ducking", action="store_true", help="Skip background music")

    args = parser.parse_args()

    # Load script
    print(f"Loading script: {args.script}", file=sys.stderr)
    script = load_script(args.script)
    print(f"Found {len(script)} lines", file=sys.stderr)
    print()

    # Generate TTS
    api_key = get_elevenlabs_key()
    voiceover_file, clips = create_timed_voiceover(script, args.voice, api_key, args.model)

    # Mix with music if provided
    if args.background_music and not args.no_ducking:
        if not Path(args.background_music).exists():
            print(f"Warning: Background music not found: {args.background_music}", file=sys.stderr)
            print(f"Skipping music mix. Saving voiceover only.", file=sys.stderr)
            import shutil
            shutil.copy(voiceover_file, args.output)
        else:
            mix_with_music(voiceover_file, args.background_music, args.output)
    else:
        import shutil
        shutil.copy(voiceover_file, args.output)

    print(f"\nDone! Output: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
