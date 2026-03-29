"""Filmstrip extraction: two frames per break (t-0.5s, t+0.5s) via ffmpeg."""
import os
import subprocess
import tempfile
import logging

from app.storage.s3 import upload_file_to_s3, get_public_url, get_s3_client
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def extract_filmstrip(video_id: str, break_id: str, break_t: float,
                      local_video_path: str) -> dict:
    """Extract before/after frames for a break and upload to S3."""
    before_key = f"filmstrips/{video_id}/{break_id}_before.jpg"
    after_key = f"filmstrips/{video_id}/{break_id}_after.jpg"

    with tempfile.TemporaryDirectory() as tmpdir:
        before_path = os.path.join(tmpdir, f"{break_id}_before.jpg")
        after_path = os.path.join(tmpdir, f"{break_id}_after.jpg")

        # Extract frame at t-0.5s
        subprocess.run([
            "ffmpeg", "-ss", str(max(0, break_t - 0.5)),
            "-i", local_video_path,
            "-frames:v", "1", "-q:v", "3",
            before_path, "-y", "-loglevel", "error"
        ], check=True)

        # Extract frame at t+0.5s
        subprocess.run([
            "ffmpeg", "-ss", str(break_t + 0.5),
            "-i", local_video_path,
            "-frames:v", "1", "-q:v", "3",
            after_path, "-y", "-loglevel", "error"
        ], check=True)

        upload_file_to_s3(before_path, before_key)
        upload_file_to_s3(after_path, after_key)

    return {
        "before_frame_url": get_public_url(before_key),
        "after_frame_url": get_public_url(after_key),
    }


def get_video_duration(local_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", local_path
    ], capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 3600.0
