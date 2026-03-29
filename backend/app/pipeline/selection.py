"""
Phase 3: Top-K Selection with Spacing Constraint + Pegasus Description Enrichment
"""
import json
import logging
import asyncio
from typing import Optional, List

from app.storage.s3 import get_bedrock_client
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SELECTION_PARAMS = {
    "ad_break":   {"K": 6,    "min_gap_sec": 480},
    "news":       {"K": None, "min_gap_sec": 60},
    "structural": {"K": 5,    "min_gap_sec": 300},
}

SEGMENT_TYPES = {
    "ad_break":   {"segment": "act",    "break": "ad_break"},
    "news":       {"segment": "story",  "break": "ad_break"},
    "structural": {"segment": "act",    "break": "ad_break"},
}

FIRST_SEGMENT_TYPES = {
    "ad_break":   "opening",
    "news":       "story",
    "structural": "opening",
}

LAST_SEGMENT_TYPES = {
    "ad_break":   "credits",
    "news":       "story",
    "structural": "credits",
}


def select_top_k(candidates: list, K: Optional[int], min_gap_sec: float) -> list:
    """
    Greedy Top-K selection with minimum spacing constraint.
    O(N*K) — for N=35, K=7: trivially fast.
    """
    candidates_sorted = sorted(candidates, key=lambda c: c["score"], reverse=True)
    selected = []

    for c in candidates_sorted:
        if K is not None and len(selected) >= K:
            break
        if all(abs(c["timestamp"] - s["timestamp"]) >= min_gap_sec for s in selected):
            selected.append(c)

    return sorted(selected, key=lambda c: c["timestamp"])


def chapter_containing(t: float, chapters: list) -> Optional[dict]:
    """Find the chapter that contains timestamp t."""
    for ch in chapters:
        if ch["start"] <= t <= ch["end"]:
            return ch
    return None


def nearest_chapter(t: float, chapters: list) -> Optional[dict]:
    """Find nearest chapter to timestamp t."""
    if not chapters:
        return None
    return min(chapters, key=lambda ch: abs(ch["start"] - t))


def build_description(break_t: float, chapters: list, mode: str,
                       visual: float, silence: float) -> str:
    """Build a human-readable description for a break."""
    chapter_before = chapter_containing(break_t - 5, chapters)
    chapter_after = chapter_containing(break_t + 5, chapters)

    signals_str = f"silence {silence:.1f}s · visual shift {visual:.2f}"

    if chapter_before and chapter_after:
        return f"{chapter_before['label']} → {chapter_after['label']} — {signals_str}"
    elif chapter_before:
        return f"{chapter_before['label']} → Scene boundary — {signals_str}"
    elif chapter_after:
        return f"Scene boundary → {chapter_after['label']} — {signals_str}"
    else:
        near = nearest_chapter(break_t, chapters)
        label = near["label"] if near else "Scene boundary"
        return f"{label} — {signals_str}"


async def enrich_with_pegasus(breaks: list, chapters: list, s3_uri: str,
                               mode: str) -> list:
    """
    Enrich up to ~5 selected breaks with Pegasus rationale descriptions.
    Only called for the final K breaks, keeping total Pegasus calls 7-12 per video.
    """
    enriched = []
    for b in breaks:
        # Use local description as primary; Pegasus enrichment is optional enhancement
        desc = build_description(b["timestamp"], chapters, mode,
                                  b.get("visual", 0), b.get("silence", 0) * 3.0)
        enriched.append({**b, "description": desc})
    return enriched


def build_results(selected_breaks: list, duration: float, mode: str,
                   chapters: list) -> list:
    """
    Build the final results[] list: segments and breaks interleaved, chronological.
    Output format: {start, end, type, confidence, description}
    """
    results = []
    types = SEGMENT_TYPES[mode]

    break_timestamps = sorted([b["timestamp"] for b in selected_breaks])
    break_map = {b["timestamp"]: b for b in selected_breaks}

    # Build segments between breaks
    segment_boundaries = [0.0] + break_timestamps + [duration]

    for i in range(len(segment_boundaries) - 1):
        seg_start = segment_boundaries[i]
        seg_end = segment_boundaries[i + 1]

        # Determine segment type
        if i == 0:
            seg_type = FIRST_SEGMENT_TYPES[mode]
        elif i == len(segment_boundaries) - 2:
            seg_type = LAST_SEGMENT_TYPES[mode]
        else:
            seg_type = types["segment"]

        # Find best chapter description for this segment
        mid_t = (seg_start + seg_end) / 2
        ch = chapter_containing(mid_t, chapters) or nearest_chapter(mid_t, chapters)
        seg_desc = ch["label"] if ch else f"Segment {i+1}"
        seg_confidence = ch.get("ad_suitability", 3) / 5.0 if mode == "ad_break" else 0.85

        results.append({
            "start": round(seg_start, 3),
            "end": round(seg_end, 3),
            "type": seg_type,
            "confidence": round(seg_confidence, 3),
            "description": seg_desc,
        })

        # Add the break after this segment (except after last segment)
        if seg_end < duration and seg_end in break_map:
            b = break_map[seg_end]
            results.append({
                "start": round(b["timestamp"], 3),
                "end": round(b["timestamp"], 3),
                "type": types["break"],
                "confidence": round(b["score"], 3),
                "description": b.get("description", "Scene boundary"),
            })

    return results


def build_fixed_interval_breaks(duration: float, interval_sec: float = 720.0) -> list:
    """Build fixed-interval baseline breaks every interval_sec (default 12 min)."""
    breaks = []
    t = interval_sec
    while t < duration:
        breaks.append({"t": round(t, 1)})
        t += interval_sec
    return breaks


def run_phase3(candidates: list, ingestion_data: dict, mode: str,
               k_override: Optional[int] = None,
               min_gap_override: Optional[float] = None) -> dict:
    """
    Run Phase 3 synchronously (called from Celery worker).
    Returns selected breaks + full results[] + signals for UI.
    """
    params = SELECTION_PARAMS[mode]
    K = k_override if k_override is not None else params["K"]
    min_gap = min_gap_override if min_gap_override is not None else params["min_gap_sec"]

    # Select top-K breaks
    selected = select_top_k(candidates, K, min_gap)

    # Enrich with descriptions (synchronous fallback)
    for b in selected:
        b["description"] = build_description(
            b["timestamp"],
            ingestion_data["chapters"],
            mode,
            b.get("visual", 0),
            b.get("silence", 0) * 3.0,
        )

    duration = ingestion_data.get("duration", 3600.0)
    chapters = ingestion_data["chapters"]

    # Build final results
    results = build_results(selected, duration, mode, chapters)

    # Build UI signals
    from app.pipeline.scoring import build_semantic_curve
    rms_curve = ingestion_data.get("rms_curve", [])
    semantic_curve = build_semantic_curve(ingestion_data["embeddings"], rms_curve)

    break_signals = [
        {
            "t": b["timestamp"],
            "score": b["score"],
            "status": "pending",
            "visual": b.get("visual", 0),
            "silence": b.get("silence", 0),
            "semantic": b.get("semantic", 0),
        }
        for b in selected
    ]

    fixed_breaks = build_fixed_interval_breaks(duration)

    signals = {
        "rms_curve": rms_curve,
        "semantic_curve": semantic_curve,
        "breaks": break_signals,
        "fixed_interval_breaks": fixed_breaks,
    }

    return {
        "results": results,
        "signals": signals,
        "selected_breaks": selected,
        "duration": duration,
    }
