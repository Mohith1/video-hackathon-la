"""
Phase 1: Multimodal Ingestion
- Job A: Marengo Embed 3.0 — frame-by-frame image embeddings via AWS Bedrock
- Job B: Pegasus 1.2 — chapter segmentation + ASR via AWS Bedrock
- Job C: Audio RMS + silence detection via librosa + ffmpeg
All three run concurrently via asyncio.gather().

Confirmed Bedrock API schemas (probed 2026-03-28):
  Marengo image: {"inputType":"image","image":{"mediaSource":{"s3Location":{"uri":..,"bucketOwner":..}}}}
  Marengo text:  {"inputType":"text","text":{"inputText":"..."}}
  Pegasus:       {"inputPrompt":"...","mediaSource":{"s3Location":{"uri":..,"bucketOwner":..}}}
"""
import asyncio
import json
import os
import re
import subprocess
import tempfile
import logging
from typing import Optional

import base64
import numpy as np
import librosa

from app.config import get_settings
from app.storage.s3 import invoke_bedrock_model, download_file_from_s3, upload_file_to_s3

logger = logging.getLogger(__name__)
settings = get_settings()

# Inference profile IDs (region-prefixed) — required for InvokeModel API
MARENGO_MODEL = "us.twelvelabs.marengo-embed-3-0-v1:0"
PEGASUS_MODEL  = "us.twelvelabs.pegasus-1-2-v1:0"

# Frame extraction interval for Marengo visual embeddings (seconds)
FRAME_INTERVAL = 10

MODE_PROMPTS = {
    "ad_break": (
        "You are analyzing a sports broadcast for ad-break placement. "
        "Identify natural pauses: timeouts, dead-ball moments, halftime, resolved plays. "
        "Score each chapter boundary by how natural an ad break would feel here. "
        'Return ONLY valid JSON: {"chapters": [{"start": 0, "end": 0, "label": "", "ad_suitability": 3}], '
        '"asr": [{"word": "", "start": 0.0, "end": 0.0}]}'
    ),
    "news": (
        "You are analyzing a news broadcast for story segmentation. "
        "Identify topic transitions: new story, new reporter, new location, subject change. "
        'Return ONLY valid JSON: {"chapters": [{"start": 0, "end": 0, "label": "", "topic": ""}], '
        '"asr": [{"word": "", "start": 0.0, "end": 0.0}]}'
    ),
    "structural": (
        "You are analyzing episodic content for structural markers. "
        "Identify act structure: cold open, act breaks, B-story transitions, credits. "
        'Return ONLY valid JSON: {"chapters": [{"start": 0, "end": 0, "label": "", "structural_type": "opening"}], '
        '"asr": [{"word": "", "start": 0.0, "end": 0.0}]}'
    ),
}


def _s3_location(uri: str) -> dict:
    """Build S3Location object required by Bedrock TwelveLabs models."""
    return {"uri": uri, "bucketOwner": settings.aws_account_id}


# ── Job A: Marengo visual embeddings ─────────────────────────────────────────

async def get_marengo_embeddings(s3_uri: str, video_id: str) -> list:
    """
    Job A: Extract frames at FRAME_INTERVAL seconds, embed each with Marengo image mode.
    Returns [{timestamp: float, embedding: float[1024]}]
    Falls back to mock data if Bedrock or S3 unavailable.
    """
    logger.info(f"[Phase1-A] Marengo embeddings via frame extraction: {s3_uri}")
    loop = asyncio.get_event_loop()

    def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            local_video = os.path.join(tmpdir, "video.mp4")

            # Download video (from S3 or local storage)
            try:
                s3_key = _s3_key_from_uri(s3_uri)
                download_file_from_s3(s3_key, local_video)
            except Exception:
                # Try streaming directly from S3 via presigned URL
                try:
                    from app.storage.s3 import get_video_stream_url
                    stream_url = get_video_stream_url(s3_uri)
                    if stream_url and stream_url.startswith("http"):
                        import urllib.request
                        logger.info(f"[Phase1-A] Downloading video from presigned URL")
                        urllib.request.urlretrieve(stream_url, local_video)
                    else:
                        raise ValueError("No stream URL")
                except Exception as e2:
                    logger.warning(f"[Phase1-A] Could not download video: {e2}. Using mock embeddings.")
                    return _generate_mock_embeddings()

            # Get video duration
            duration = _get_duration(local_video)
            timestamps = list(np.arange(0, duration, FRAME_INTERVAL))
            logger.info(f"[Phase1-A] Extracting {len(timestamps)} frames over {duration:.0f}s")

            embeddings = []
            for t in timestamps:
                frame_path = os.path.join(tmpdir, f"frame_{t:.0f}.jpg")

                # Extract frame with ffmpeg
                result = subprocess.run([
                    "ffmpeg", "-ss", str(t), "-i", local_video,
                    "-frames:v", "1", "-q:v", "3",
                    frame_path, "-y", "-loglevel", "error"
                ], capture_output=True)

                if not os.path.exists(frame_path):
                    logger.warning(f"[Phase1-A] Frame extraction failed at t={t}")
                    continue

                # Use base64 — no S3 upload needed for Marengo image embeddings
                try:
                    with open(frame_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    emb = _marengo_image_embedding_b64(b64)
                except Exception as e:
                    logger.warning(f"[Phase1-A] Frame embed failed at t={t}: {e}")
                    emb = _marengo_text_embedding(f"video frame at {t:.0f}s")

                embeddings.append({"timestamp": float(t), "embedding": emb})

            if not embeddings:
                logger.warning("[Phase1-A] No embeddings produced, using mock.")
                return _generate_mock_embeddings()

            logger.info(f"[Phase1-A] Got {len(embeddings)} embeddings")
            return embeddings

    return await loop.run_in_executor(None, _run)


def _marengo_image_embedding_b64(b64_string: str) -> list:
    """
    Call Marengo with a base64-encoded image.
    No S3 needed — works entirely locally.
    Response: {"data": [{"embedding": [float, ...]}]}
    """
    result = invoke_bedrock_model(MARENGO_MODEL, {
        "inputType": "image",
        "image": {
            "mediaSource": {"base64String": b64_string},
        },
    })
    return _extract_embedding(result)


def _marengo_text_embedding(text: str) -> list:
    """Call Marengo text embedding — fallback when frame extraction fails."""
    result = invoke_bedrock_model(MARENGO_MODEL, {
        "inputType": "text",
        "text": {"inputText": text},
    })
    return _extract_embedding(result)


def _extract_embedding(result: dict) -> list:
    """
    Parse Marengo embedding from response.
    Notebook shows: result["data"] where data is a list of embedding dicts.
    Each item: {"embedding": [float, ...]} or just [float, ...]
    """
    data = result.get("data", [])
    if not data:
        return []
    first = data[0]
    if isinstance(first, dict):
        return first.get("embedding", [])
    if isinstance(first, list):
        return first
    return data


def _generate_mock_embeddings(duration_sec: float = 3600.0) -> list:
    """Mock embeddings for local dev without S3."""
    embeddings = []
    np.random.seed(42)
    base = np.random.randn(1024)
    n = int(duration_sec // FRAME_INTERVAL)
    for i in range(n):
        t = i * FRAME_INTERVAL
        if i % 30 == 0:
            base = np.random.randn(1024)
        elif i % 10 == 0:
            base = base + np.random.randn(1024) * 0.5
        emb = base + np.random.randn(1024) * 0.1
        emb = emb / np.linalg.norm(emb)
        embeddings.append({"timestamp": float(t), "embedding": emb.tolist()})
    return embeddings


# ── Job B: Pegasus chapter segmentation ──────────────────────────────────────

async def get_pegasus_chapters(s3_uri: str, mode: str) -> dict:
    """
    Job B: Get Pegasus chapter segmentation + ASR via AWS Bedrock.
    API: {"inputPrompt": "...", "mediaSource": {"s3Location": {"uri": ..., "bucketOwner": ...}}}
    """
    logger.info(f"[Phase1-B] Pegasus chapters: {s3_uri} mode={mode}")
    loop = asyncio.get_event_loop()

    def _call():
        prompt = MODE_PROMPTS.get(mode, MODE_PROMPTS["ad_break"])

        # Bedrock requires real S3 URI (can't use local://)
        if s3_uri.startswith("local://"):
            logger.warning("[Phase1-B] Video is local — Pegasus requires S3. Using mock chapters.")
            return _generate_mock_chapters(mode)

        try:
            result = invoke_bedrock_model(PEGASUS_MODEL, {
                "inputPrompt": prompt,
                "mediaSource": {
                    "s3Location": _s3_location(s3_uri),
                },
                "temperature": 0.2,
            })
            # Pegasus response: {"message": "...", "stopReason": "end_turn"}
            raw = result.get("message", "")
            return _parse_pegasus_response(raw, mode)
        except Exception as e:
            logger.warning(f"[Phase1-B] Pegasus error: {e}. Using mock chapters.")
            return _generate_mock_chapters(mode)

    return await loop.run_in_executor(None, _call)


def _pegasus_schema(mode: str) -> dict:
    """JSON Schema for Pegasus responseFormat — ensures structured output."""
    chapter_props: dict = {
        "start": {"type": "number"},
        "end":   {"type": "number"},
        "label": {"type": "string"},
    }
    if mode == "ad_break":
        chapter_props["ad_suitability"] = {"type": "integer", "minimum": 1, "maximum": 5}
    elif mode == "news":
        chapter_props["topic"] = {"type": "string"}
    else:
        chapter_props["structural_type"] = {"type": "string"}

    return {
        "type": "object",
        "properties": {
            "chapters": {
                "type": "array",
                "items": {"type": "object", "properties": chapter_props,
                          "required": ["start", "end", "label"]},
            },
            "asr": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "word":  {"type": "string"},
                        "start": {"type": "number"},
                        "end":   {"type": "number"},
                    },
                    "required": ["word", "start", "end"],
                },
            },
        },
        "required": ["chapters"],
    }


def _parse_pegasus_response(raw: str, mode: str) -> dict:
    """Extract JSON from Pegasus response text."""
    if isinstance(raw, dict):
        return {
            "chapters": raw.get("chapters", []),
            "asr": raw.get("asr", []),
        }
    try:
        # Try to extract JSON block from text response
        match = re.search(r'\{.*\}', str(raw), re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "chapters": data.get("chapters", []),
                "asr": data.get("asr", []),
            }
    except Exception:
        pass
    logger.warning("[Phase1-B] Could not parse Pegasus response, using mock.")
    return _generate_mock_chapters(mode)


def _generate_mock_chapters(mode: str) -> dict:
    if mode == "ad_break":
        chapters = [
            {"start": 0.0,    "end": 751.3,  "label": "Pre-game coverage",          "ad_suitability": 2},
            {"start": 751.3,  "end": 1455.0, "label": "First quarter",               "ad_suitability": 4},
            {"start": 1455.0, "end": 2100.0, "label": "Timeout break Q1",            "ad_suitability": 5},
            {"start": 2100.0, "end": 2800.0, "label": "Second quarter",              "ad_suitability": 3},
            {"start": 2800.0, "end": 3200.0, "label": "Halftime show",               "ad_suitability": 5},
            {"start": 3200.0, "end": 3900.0, "label": "Third quarter",               "ad_suitability": 3},
            {"start": 3900.0, "end": 4500.0, "label": "Fourth quarter - close game", "ad_suitability": 2},
        ]
    elif mode == "news":
        chapters = [
            {"start": 0.0,    "end": 300.0,  "label": "Opening headlines",       "topic": "introduction"},
            {"start": 300.0,  "end": 900.0,  "label": "Breaking: Economic report","topic": "economy"},
            {"start": 900.0,  "end": 1500.0, "label": "Weather update",           "topic": "weather"},
            {"start": 1500.0, "end": 2100.0, "label": "Sports highlights",        "topic": "sports"},
            {"start": 2100.0, "end": 2700.0, "label": "International news",       "topic": "international"},
            {"start": 2700.0, "end": 3300.0, "label": "Local stories",            "topic": "local"},
            {"start": 3300.0, "end": 3600.0, "label": "Closing remarks",          "topic": "close"},
        ]
    else:
        chapters = [
            {"start": 0.0,    "end": 120.0,  "label": "Cold open",           "structural_type": "opening"},
            {"start": 120.0,  "end": 900.0,  "label": "Act 1 - setup",       "structural_type": "act"},
            {"start": 900.0,  "end": 1680.0, "label": "Act 2 - confrontation","structural_type": "act"},
            {"start": 1680.0, "end": 2100.0, "label": "B-story transition",   "structural_type": "transition"},
            {"start": 2100.0, "end": 2520.0, "label": "Act 3 - resolution",   "structural_type": "act"},
            {"start": 2520.0, "end": 2640.0, "label": "Tag/Credits",          "structural_type": "credits"},
        ]
    asr = []
    for ch in chapters:
        for t in np.arange(ch["start"], ch["end"], 5.0):
            asr.append({"word": "word", "start": float(t), "end": float(t + 0.3)})
    return {"chapters": chapters, "asr": asr}


# ── Job C: Audio signals ──────────────────────────────────────────────────────

async def extract_audio_signals(s3_uri: str, video_id: str) -> dict:
    """Job C: Extract audio RMS and silence curves via librosa + ffmpeg."""
    logger.info(f"[Phase1-C] Audio signals for {video_id}")
    loop = asyncio.get_event_loop()

    def _extract():
        with tempfile.TemporaryDirectory() as tmpdir:
            local_video = os.path.join(tmpdir, "video.mp4")
            local_audio = os.path.join(tmpdir, "audio.wav")

            try:
                s3_key = _s3_key_from_uri(s3_uri)
                download_file_from_s3(s3_key, local_video)
            except Exception as e:
                logger.warning(f"[Phase1-C] Could not download video: {e}. Using mock audio.")
                return _generate_mock_audio_signals()

            # Extract mono audio
            subprocess.run([
                "ffmpeg", "-i", local_video, "-vn", "-acodec", "pcm_s16le",
                "-ar", "22050", "-ac", "1", local_audio, "-y", "-loglevel", "error"
            ], check=True)

            y, sr = librosa.load(local_audio, sr=22050, mono=True)
            duration = len(y) / sr

            # RMS per second
            rms = librosa.feature.rms(y=y, hop_length=sr)[0]
            rms_curve = [{"t": float(i), "rms": float(v)} for i, v in enumerate(rms)]

            # Silence detection
            proc = subprocess.run([
                "ffmpeg", "-i", local_audio,
                "-af", "silencedetect=noise=-30dB:d=0.3",
                "-f", "null", "-", "-loglevel", "info"
            ], capture_output=True, text=True)

            silence_curve = [0.0] * (int(duration) + 1)
            starts = re.findall(r"silence_start: (\d+\.?\d*)", proc.stderr)
            ends   = re.findall(r"silence_end: (\d+\.?\d*)", proc.stderr)
            for s, e in zip(starts, ends):
                s_t, e_t = float(s), float(e)
                for t in range(int(s_t), min(int(e_t) + 1, len(silence_curve))):
                    silence_curve[t] = min(silence_curve[t] + (e_t - s_t), 3.0)

            return {"silence": silence_curve, "rms": rms_curve, "duration": duration}

    return await loop.run_in_executor(None, _extract)


def _generate_mock_audio_signals(duration_sec: float = 3600.0) -> dict:
    np.random.seed(42)
    n = int(duration_sec)
    rms_vals = np.abs(np.random.randn(n) * 0.3 + 0.5)
    for i in range(0, n, 480):
        rms_vals[i:i+10] = np.random.uniform(0.02, 0.1, 10)
    rms_curve = [{"t": float(i), "rms": float(v)} for i, v in enumerate(rms_vals)]
    silence_curve = [0.0 if rms_vals[i] > 0.15 else float(np.random.uniform(0.5, 2.5))
                     for i in range(n)]
    return {"silence": silence_curve, "rms": rms_curve, "duration": duration_sec}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _s3_key_from_uri(uri: str) -> str:
    """Strip s3://bucket/ or local:// prefix to get the key."""
    if uri.startswith("local://"):
        return uri.replace("local://", "")
    return uri.replace(f"s3://{settings.s3_bucket}/", "")


def _get_duration(video_path: str) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path
    ], capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 3600.0


# ── Entry point ───────────────────────────────────────────────────────────────

async def run_ingestion(s3_uri: str, mode: str, video_id: str) -> dict:
    """
    Run all 3 ingestion jobs concurrently.
    Wall clock = max(A, B, C), not A+B+C.
    """
    logger.info(f"[Phase1] Parallel ingestion: video={video_id} mode={mode} uri={s3_uri}")

    embeddings, chapters_result, audio_signals = await asyncio.gather(
        get_marengo_embeddings(s3_uri, video_id),
        get_pegasus_chapters(s3_uri, mode),
        extract_audio_signals(s3_uri, video_id),
    )

    return {
        "embeddings":    embeddings,
        "chapters":      chapters_result["chapters"],
        "asr":           chapters_result["asr"],
        "silence_curve": audio_signals["silence"],
        "rms_curve":     audio_signals["rms"],
        "duration":      audio_signals.get("duration", 3600.0),
    }
