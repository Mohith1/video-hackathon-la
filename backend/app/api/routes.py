"""FastAPI route handlers for SegmentIQ."""
import asyncio
import json
import uuid
import tempfile
import os
import logging
from typing import Optional, List

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form, Body
from fastapi.responses import StreamingResponse, JSONResponse
import io

from app.models import (
    VideoStatus, ProcessingStatus, ProcessingMode,
    OptimizeRequest, ExportFormat
)
from app.storage.s3 import (
    upload_file_to_s3, download_file_from_s3, get_public_url,
    get_video_stream_url, put_object, get_object, head_object,
)
from app.storage.dynamodb import (
    create_video_record, get_video_record, update_video_status
)
from app.config import get_settings
from app.pipeline.export import to_json, to_xml, to_edl

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


def _run_pipeline(video_id: str, s3_uri: str, mode: str):
    """Run the full 3-phase pipeline synchronously (called in background thread)."""
    import asyncio
    import time
    from app.pipeline.ingestion import run_ingestion
    from app.pipeline.scoring import collect_candidates, score_all_candidates
    from app.pipeline.selection import run_phase3

    try:
        pipeline_start = time.time()

        # Phase 1
        update_video_status(video_id, status="phase1", progress=10)
        ingestion_data = asyncio.run(run_ingestion(s3_uri, mode, video_id))
        update_video_status(video_id, status="phase1", progress=60,
                            duration=ingestion_data.get("duration", 3600.0))

        # Phase 2
        update_video_status(video_id, status="phase2", progress=70)
        candidates = collect_candidates(
            ingestion_data["chapters"],
            ingestion_data["silence_curve"],
            ingestion_data["embeddings"],  # Marengo visual candidates always included
        )
        scored = score_all_candidates(
            candidates, ingestion_data["embeddings"],
            ingestion_data["chapters"], ingestion_data["silence_curve"], mode
        )
        update_video_status(video_id, status="phase2", progress=80)

        # Phase 3
        update_video_status(video_id, status="phase3", progress=85)
        phase3 = run_phase3(scored, ingestion_data, mode)

        processing_time = round(time.time() - pipeline_start, 1)
        video_duration = phase3["duration"]
        # Real-time ratio: how many seconds of video processed per second of wall time
        rt_ratio = round(video_duration / processing_time, 1) if processing_time > 0 else 0

        # Save results
        update_video_status(
            video_id,
            status="complete",
            progress=100,
            results=phase3["results"],
            signals=phase3["signals"],
            duration=phase3["duration"],
            processing_time_sec=processing_time,
            realtime_ratio=rt_ratio,
        )

        # Cache ingestion data for re-optimization
        try:
            put_object(
                f"cache/{video_id}/ingestion.json",
                json.dumps({
                    "embeddings": ingestion_data["embeddings"],
                    "chapters": ingestion_data["chapters"],
                    "silence_curve": ingestion_data["silence_curve"],
                    "rms_curve": ingestion_data["rms_curve"],
                    "duration": ingestion_data.get("duration", 3600.0),
                }),
                content_type="application/json",
            )
        except Exception as e:
            logger.warning(f"Could not cache ingestion data: {e}")

        logger.info(f"Pipeline complete for video {video_id}")

    except Exception as e:
        logger.error(f"Pipeline failed for video {video_id}: {e}", exc_info=True)
        update_video_status(video_id, status="failed", error=str(e))


@router.post("/videos")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form(default="ad_break"),
):
    """
    Upload a video and start the segmentation pipeline.
    When AWS credentials are set (production), the video is uploaded to S3 first.
    When running locally without credentials, files are stored in local_uploads/.
    Pegasus requires an S3 URI — if no credentials, it falls back to mock chapters.
    """
    video_id = str(uuid.uuid4())
    filename = file.filename or f"{video_id}.mp4"
    s3_key = f"videos/{video_id}/{filename}"

    # Stream upload to a temp file first
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # upload_file_to_s3 returns s3://... when AWS_ACCESS_KEY_ID is set
        # or local://... when running without S3 credentials (local dev)
        s3_uri = upload_file_to_s3(tmp_path, s3_key)
        logger.info(f"Video stored at: {s3_uri}")
    except Exception as upload_err:
        logger.warning(f"S3 upload failed ({upload_err}), falling back to local storage")
        try:
            import shutil
            local_dir = os.path.join(os.path.dirname(__file__), "..", "..", "local_uploads", os.path.dirname(s3_key))
            os.makedirs(local_dir, exist_ok=True)
            local_dest = os.path.join(os.path.dirname(__file__), "..", "..", "local_uploads", s3_key)
            shutil.copy2(tmp_path, local_dest)
            s3_uri = f"local://{s3_key}"
        except Exception as e2:
            logger.error(f"Local fallback also failed: {e2}")
            s3_uri = f"local://{s3_key}"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    create_video_record(video_id, mode, s3_uri, filename)
    background_tasks.add_task(_run_pipeline, video_id, s3_uri, mode)

    return {"video_id": video_id, "status": "processing", "mode": mode, "stored_at": s3_uri}


@router.post("/videos/import-s3")
async def import_s3_video(
    background_tasks: BackgroundTasks,
    s3_uri: str = Body(...),
    mode: str = Body(default="structural"),
    filename: str = Body(default=""),
):
    """Trigger the pipeline for an existing video in S3 (no upload needed)."""
    if not s3_uri.startswith("s3://"):
        raise HTTPException(status_code=400, detail="s3_uri must start with s3://")

    video_id = str(uuid.uuid4())
    display_name = filename or s3_uri.split("/")[-1] or "imported-video.mp4"

    create_video_record(video_id, mode, s3_uri, display_name)
    background_tasks.add_task(_run_pipeline, video_id, s3_uri, mode)

    return {"video_id": video_id, "status": "processing", "mode": mode, "s3_uri": s3_uri}


@router.get("/videos/{video_id}")
async def get_video_status(video_id: str):
    """Get video processing status and results."""
    record = get_video_record(video_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")

    # Add video stream URL
    s3_uri = record.get("s3_uri", "")
    if s3_uri:
        record["video_url"] = get_video_stream_url(s3_uri)

    return record


@router.post("/videos/{video_id}/optimize")
async def re_optimize(video_id: str, req: OptimizeRequest, background_tasks: BackgroundTasks):
    """Re-run Phase 3 with new mode/K/min_gap parameters."""
    record = get_video_record(video_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    if record.get("status") not in ("complete", "failed"):
        raise HTTPException(status_code=409, detail="Pipeline not complete yet")

    # Load cached ingestion data
    try:
        ingestion_data = json.loads(get_object(f"cache/{video_id}/ingestion.json"))
    except Exception:
        raise HTTPException(status_code=422, detail="Cached ingestion data not available. Re-process the video.")

    from app.pipeline.scoring import collect_candidates, score_all_candidates
    from app.pipeline.selection import run_phase3

    mode = req.mode.value
    candidates = collect_candidates(
        ingestion_data["chapters"],
        ingestion_data["silence_curve"],
        ingestion_data.get("embeddings"),
    )
    scored = score_all_candidates(
        candidates, ingestion_data["embeddings"],
        ingestion_data["chapters"], ingestion_data["silence_curve"], mode
    )
    phase3 = run_phase3(scored, ingestion_data, mode,
                        k_override=req.k, min_gap_override=req.min_gap_sec)

    update_video_status(
        video_id,
        mode=mode,
        results=phase3["results"],
        signals=phase3["signals"],
        status="complete",
    )

    return {"video_id": video_id, "status": "complete", "mode": mode,
            "results": phase3["results"], "signals": phase3["signals"]}


@router.get("/videos/{video_id}/export")
async def export_results(video_id: str, format: str = "json"):
    """Export segmentation results as JSON, XML, or EDL."""
    record = get_video_record(video_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")
    if record.get("status") != "complete":
        raise HTTPException(status_code=409, detail="Processing not complete")

    results = record.get("results", [])
    duration = record.get("duration", 0.0)
    mode = record.get("mode", "ad_break")
    content_type = record.get("content_type", "video")

    if format == "json":
        content = to_json(video_id, duration, content_type, mode, results)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=segmentiq_{video_id}.json"}
        )
    elif format == "xml":
        content = to_xml(video_id, duration, content_type, mode, results)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename=segmentiq_{video_id}.xml"}
        )
    elif format == "edl":
        content = to_edl(video_id, results)
        return StreamingResponse(
            io.BytesIO(content.encode()),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=segmentiq_{video_id}.edl"}
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Use json, xml, or edl.")


@router.get("/videos/{video_id}/breaks/{break_id}/filmstrip")
async def get_filmstrip(video_id: str, break_id: str):
    """Get before/after filmstrip frames for a break point."""
    record = get_video_record(video_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")

    before_key = f"filmstrips/{video_id}/{break_id}_before.jpg"
    after_key = f"filmstrips/{video_id}/{break_id}_after.jpg"

    # Return cached frames if already extracted
    if head_object(before_key):
        return {
            "before_frame_url": get_public_url(before_key),
            "after_frame_url": get_public_url(after_key),
        }

    # Resolve break timestamp
    signals = record.get("signals", {})
    breaks = signals.get("breaks", [])
    try:
        break_idx = int(break_id)
        if break_idx >= len(breaks):
            raise HTTPException(status_code=404, detail="Break not found")
        break_t = breaks[break_idx]["t"]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid break_id")

    # Download video locally, extract frames, re-upload
    s3_uri = record.get("s3_uri", "")
    s3_key = s3_uri.replace(f"s3://{settings.s3_bucket}/", "").replace("local://", "")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        local_video = tmp.name

    try:
        download_file_from_s3(s3_key, local_video)
        from app.pipeline.filmstrip import extract_filmstrip
        result = extract_filmstrip(video_id, break_id, break_t, local_video)
        return result
    except Exception as e:
        logger.error(f"Filmstrip extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(local_video):
            os.unlink(local_video)


@router.post("/videos/{video_id}/breaks/{break_id}/generate-transition")
async def generate_transition(video_id: str, break_id: str):
    """Generate LTX Video transition bumper for a break."""
    record = get_video_record(video_id)
    if not record:
        raise HTTPException(status_code=404, detail="Video not found")

    results = record.get("results", [])
    signals = record.get("signals", {})
    breaks = signals.get("breaks", [])

    try:
        break_idx = int(break_id)
        if break_idx >= len(breaks):
            raise HTTPException(status_code=404, detail="Break not found")
        break_t = breaks[break_idx]["t"]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid break_id")

    # Find segments before and after
    seg_before = next((r for r in reversed(results) if r["start"] < break_t and r["end"] <= break_t), None)
    seg_after = next((r for r in results if r["start"] >= break_t), None)

    desc_before = seg_before["description"] if seg_before else "Previous segment"
    desc_after = seg_after["description"] if seg_after else "Next segment"

    # Placeholder: LTX Video integration
    # In production, call LTX Video API here
    return {
        "status": "unavailable",
        "message": "LTX Video integration not configured. Provide LTX_API_KEY to enable.",
        "prompt": f'Generate a 3-second visual bumper transitioning between:\nFROM: "{desc_before}"\nTO: "{desc_after}"\nStyle: broadcast quality, smooth, no text overlays.',
    }
