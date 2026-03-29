"""
Phase 2: Boundary Scoring
Compute a weighted composite score for each candidate timestamp.
Score(t) = w1*visual(t) + w2*silence(t) + w3*semantic(t)
"""
import numpy as np
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

WEIGHTS = {
    "ad_break":   {"visual": 0.25, "silence": 0.40, "semantic": 0.35},
    "news":       {"visual": 0.30, "silence": 0.10, "semantic": 0.60},
    "structural": {"visual": 0.35, "silence": 0.15, "semantic": 0.50},
}

THRESHOLDS = {
    "ad_break":   0.45,
    "news":       0.50,
    "structural": 0.40,
}


def cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two embedding vectors."""
    a = np.array(a, dtype=np.float32)
    b = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def embedding_at(t: float, embeddings: list) -> Optional[list]:
    """Find embedding closest to timestamp t."""
    if not embeddings:
        return None
    closest = min(embeddings, key=lambda e: abs(e["timestamp"] - t))
    return closest["embedding"]


def chapter_score_at(t: float, chapters: list, mode: str) -> float:
    """
    Returns 0.0 if t is not near a chapter boundary.
    Returns ad_suitability/5 (ad_break) or 1.0 (news/structural) if at a boundary.
    """
    TOLERANCE = 15.0  # seconds — within 15s of chapter start = boundary
    for ch in chapters:
        if abs(ch["start"] - t) < TOLERANCE:
            if mode == "ad_break":
                return ch.get("ad_suitability", 3) / 5.0
            else:
                return 1.0
    return 0.0


def silence_score_at(t: float, silence_curve: list) -> float:
    """Normalize silence duration at timestamp t to [0,1], capped at 3s."""
    idx = int(t)
    if idx < 0 or idx >= len(silence_curve):
        return 0.0
    return min(silence_curve[idx], 3.0) / 3.0


def boundary_score(t: float, embeddings: list, chapters: list,
                   silence_curve: list, mode: str) -> dict:
    """Compute the composite boundary score for timestamp t."""
    w = WEIGHTS[mode]

    # Signal 1: Visual semantic shift (Marengo cosine distance)
    emb_before = embedding_at(t - 5, embeddings)
    emb_after = embedding_at(t + 5, embeddings)
    if emb_before and emb_after:
        visual = 1.0 - cosine_similarity(emb_before, emb_after)
    else:
        visual = 0.0

    # Signal 2: Audio silence
    silence = silence_score_at(t, silence_curve)

    # Signal 3: Pegasus semantic boundary
    semantic = chapter_score_at(t, chapters, mode)

    score = w["visual"] * visual + w["silence"] * silence + w["semantic"] * semantic

    return {
        "timestamp": t,
        "score": round(score, 4),
        "visual": round(visual, 4),
        "silence": round(silence, 4),
        "semantic": round(semantic, 4),
    }


def collect_visual_candidates(embeddings: list, threshold: float = 0.25) -> List[float]:
    """
    Find timestamps where Marengo visual embeddings shift significantly.
    Cosine distance > threshold between consecutive frames = scene boundary candidate.
    This gives real visual scene-change detection from Marengo even without Pegasus.
    """
    candidates = []
    for i in range(1, len(embeddings)):
        dist = 1.0 - cosine_similarity(
            embeddings[i - 1]["embedding"], embeddings[i]["embedding"]
        )
        if dist > threshold and embeddings[i]["timestamp"] > 0:
            candidates.append(embeddings[i]["timestamp"])
    return candidates


def collect_candidates(chapters: list, silence_curve: list,
                       embeddings: list = None) -> List[float]:
    """
    Collect candidate timestamps from three real signals:
    1. Pegasus chapter boundaries (semantic understanding)
    2. Silence peaks from audio (pause detection)
    3. Marengo visual embedding shifts (scene-change detection)
    Sources 2 and 3 are always real signal — they drive detection even without S3/Pegasus.
    """
    candidates = set()

    # Pegasus chapter boundaries — skip t=0 (start of video is never a break)
    for ch in chapters:
        if ch["start"] > 0:
            candidates.add(ch["start"])

    # Silence candidates (timestamps where silence_curve > 0.5s)
    for i, s in enumerate(silence_curve):
        if s > 0.5:
            candidates.add(float(i))

    # Marengo visual boundary candidates (real signal from embedding distance)
    if embeddings:
        for t in collect_visual_candidates(embeddings):
            candidates.add(t)

    logger.info(f"[Phase2] Collected {len(candidates)} candidates "
                f"(chapters={sum(1 for ch in chapters if ch['start']>0)}, "
                f"silence={sum(1 for s in silence_curve if s>0.5)}, "
                f"visual={len(collect_visual_candidates(embeddings)) if embeddings else 0})")
    return sorted(list(candidates))


def score_all_candidates(candidates: List[float], embeddings: list,
                         chapters: list, silence_curve: list, mode: str) -> list:
    """Score all candidates and filter by threshold."""
    threshold = THRESHOLDS[mode]
    scored = []

    for t in candidates:
        result = boundary_score(t, embeddings, chapters, silence_curve, mode)
        if result["score"] >= threshold:
            scored.append(result)

    logger.info(f"[Phase2] {len(candidates)} candidates → {len(scored)} above threshold={threshold}")
    return sorted(scored, key=lambda x: x["score"], reverse=True)


def build_semantic_curve(embeddings: list, rms_curve: list) -> list:
    """Build a per-second semantic score for the signal timeline UI."""
    if not embeddings or len(embeddings) < 2:
        return [{"t": r["t"], "score": 0.0} for r in rms_curve]

    semantic = []
    for i in range(len(rms_curve)):
        t = float(i)
        emb_before = embedding_at(t - 5, embeddings)
        emb_after = embedding_at(t + 5, embeddings)
        if emb_before and emb_after:
            score = 1.0 - cosine_similarity(emb_before, emb_after)
        else:
            score = 0.0
        semantic.append({"t": t, "score": round(score, 4)})

    return semantic
