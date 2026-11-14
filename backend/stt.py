"""
Speech-To-Text
Audio transcription using Whisper
Model loads only for the first recording
"""

import os
import threading
from pathlib import Path

from dotenv import load_dotenv

from .schemas import ClarificationNeeded


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny.en")
MAX_VOICE_SECONDS = 60
_model = None
_lock = threading.Lock()


def transcribe(path: Path) -> str:
    """Decode audio, check duration/quality, and return text for the shared checker."""
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        from av.error import FFmpegError

        try:
            segments, info = _model.transcribe(str(path), vad_filter=True, beam_size=5)
            if info.duration > MAX_VOICE_SECONDS:
                raise ClarificationNeeded(f"Please send audio no longer than {MAX_VOICE_SECONDS} seconds.")
            parts = list(segments)
        except FFmpegError as exc:
            raise ClarificationNeeded("The audio could not be decoded. Please upload a valid audio file.") from exc

    if (info.language != "en" or info.language_probability < 0.8 or not parts
            or any(s.avg_logprob < -1 or s.no_speech_prob > 0.5 or s.compression_ratio > 2.4 for s in parts)):
        raise ClarificationNeeded("The English speech was unclear. Please type the claim or resend it clearly.")
    text = " ".join(s.text.strip() for s in parts).strip()
    if not text:
        raise ClarificationNeeded("No clear speech was detected. Please type your claim.")
    return text
