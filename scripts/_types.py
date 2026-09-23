"""Domain types shared across the scripts."""

from typing import NewType

# faster-whisper's `model_size_or_path`: a short name it knows, a Hugging Face
# repo id, or a local directory -- all plain `str` to every SDK this repo calls.
ModelName = NewType("ModelName", str)
