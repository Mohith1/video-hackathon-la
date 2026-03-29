# SegmentIQ — Minimum Viable Winning Product (MVWP)

**Version:** 1.0 (MVWP Narrowing)
**Date:** March 28, 2026
**Track:** Challenge Track 2 — Intelligent Segmentation
**Relationship to PRD v2.0:** This document narrows the research-grade PRD to a 48–72 hour buildable scope. The core thesis is identical. The algorithm is simplified from 6 phases to 3. The optimizer is replaced by a weighted scoring heuristic. Three separate workflow architectures collapse to one engine with three prompt presets.

---

## 1. Product Vision

SegmentIQ is an AI-powered video segmentation system that identifies **meaningful narrative boundaries** in long-form video (45–90 min) and places ad breaks, story boundaries, and structural markers at the moments viewers are most receptive — not at arbitrary intervals.

**Core thesis (unchanged):** TwelveLabs provides the perception layer (Marengo for visual embeddings, Pegasus for semantic reasoning). SegmentIQ provides the decision layer — a multimodal scoring engine that transforms raw perception into ranked editorial decisions. This decision intelligence does not exist in TwelveLabs' current ecosystem.

**What changes from PRD v2.0:** The 6-phase research pipeline is narrowed to 3 phases. The Dynamic Programming optimizer is replaced by a threshold-based weighted heuristic — simpler to implement, equally explainable, and directionally equivalent in output quality for the demo. The three workflow architectures are unified into one engine with mode-switched Pegasus system prompts.

---

## 2. Target Workflows — One Engine, Three Modes

All three challenge workflows run through the **same 3-phase pipeline**. What changes per mode is the Pegasus system prompt and the target segment count. No separate code paths.

| Mode | Content Type | Pegasus Focus | Target Segments |
|---|---|---|---|
| **Ad-Break** | Sports broadcast (90 min) | "Find natural pauses — dead ball, timeout, resolved tension. Score boundaries where viewer can tolerate interruption." | 5–7 ad breaks |
| **News** | News program (60 min) | "Find topic shifts — when does the story change, who is the new speaker, what is the new subject?" | Story boundaries (variable) |
| **Structural** | Episodic content (45 min) | "Find act structure — cold open, act breaks, B-story transitions, credits." | Opening, acts, credits |

The user selects the mode before processing. The mode sets the system prompt and the K parameter (number of top boundaries to return). Everything else is identical.

---

## 3. Algorithm — 3-Phase Multimodal Scoring Pipeline

### 3.1 Pipeline Overview

```
VIDEO FILE (MP4/MOV/MKV, 45–90 min)
              │
  ╔═══════════╧══════════════════════╗
  ║  PHASE 1: Multimodal Ingestion    ║
  ║  Marengo embeddings (Bedrock)     ║
  ║  Pegasus chapters + ASR (Bedrock) ║
  ║  Audio RMS + silence (librosa)    ║
  ╚═══════════╤══════════════════════╝
              │ Embeddings, captions, ASR transcript, audio signals
              │
  ╔═══════════╧══════════════════════╗
  ║  PHASE 2: Boundary Scoring        ║
  ║  For each candidate timestamp t:  ║
  ║  Score(t) = w₁·visual(t)          ║
  ║           + w₂·silence(t)         ║
  ║           + w₃·semantic(t)        ║
  ║  Select candidates: Score(t) > θ  ║
  ╚═══════════╤══════════════════════╝
              │ Ranked boundary candidates with scores
              │
  ╔═══════════╧══════════════════════╗
  ║  PHASE 3: Top-K Selection         ║
  ║  Pick K non-overlapping breaks    ║
  ║  with min spacing enforced.       ║
  ║  Attach Pegasus rationale to each.║
  ╚═══════════╤══════════════════════╝
              │
          results[]  →  Editor Review UI  →  Export JSON
```

### 3.2 Phase 1 — Multimodal Ingestion

**Goal:** Extract all signals needed for scoring in one parallel batch.

Three jobs run concurrently the moment a video is uploaded to S3:

**Job A — Marengo Embed 3.0 (via Bedrock)**

Splits the video into overlapping 10-second segments, fetches a 768-dim embedding for each from Marengo Embed 3.0 via Bedrock. Embeddings are stored in S3 Vectors.

```python
response = bedrock.invoke_model(
    modelId="twelvelabs.marengo-embed-3-0",
    body=json.dumps({"video_uri": s3_uri, "embedding_type": "temporal"})
)
embeddings = json.loads(response["body"].read())["embeddings"]
# → [{timestamp: float, embedding: float[768]}, ...]
```

**Job B — Pegasus 1.2 (via Bedrock)**

Two Pegasus calls in parallel:
1. **Chapter segmentation** — "Segment this video into chapters with topic labels and summaries."
2. **ASR transcript** — Full transcript with word-level timestamps.

```python
chapters = bedrock.invoke_model(modelId="twelvelabs.pegasus-1-2",
    body=json.dumps({"video_uri": s3_uri, "task": "chapter_segmentation",
                     "include_asr": True, "system_prompt": MODE_PROMPTS[mode]}))
```

**Mode system prompts:**

```python
MODE_PROMPTS = {
    "ad_break": """You are analyzing a sports broadcast for ad-break placement.
Identify natural pauses: timeouts, dead-ball moments, halftime, resolved plays.
Score each chapter boundary by how natural an ad break would feel here.
Return JSON: {"chapters": [{"start": t, "end": t, "label": str, "ad_suitability": 1-5}]}""",

    "news": """You are analyzing a news broadcast for story segmentation.
Identify topic transitions: new story, new reporter, new location, subject change.
Return JSON: {"chapters": [{"start": t, "end": t, "label": str, "topic": str}]}""",

    "structural": """You are analyzing episodic content for structural markers.
Identify act structure: cold open, act 1 start, act breaks, B-story, tag/credits.
Return JSON: {"chapters": [{"start": t, "end": t, "label": str,
              "structural_type": "opening|act|transition|credits"}]}"""
}
```

**Job C — Audio Extraction (librosa + ffmpeg)**

Computes two signals at 1-second resolution:
- `silence_curve[]` — duration of silence at each second (ffmpeg `silencedetect`)
- `rms_curve[]` — audio RMS energy per second (librosa `feature.rms`)

Cost: ~3 min on CPU, runs in parallel with A and B.

**Parallel execution — all three jobs via `asyncio.gather()`:**

```python
async def run_ingestion(s3_uri: str, mode: str, video_id: str) -> dict:
    """
    All three ingestion jobs run concurrently.
    Total wall clock = max(A, B, C) ≈ 20-25 min, not A+B+C ≈ 50 min.
    """
    embeddings, chapters_result, audio_signals = await asyncio.gather(
        get_marengo_embeddings(s3_uri),           # Job A: ~15-25 min
        get_pegasus_chapters(s3_uri, mode),        # Job B: ~15-25 min
        extract_audio_signals(s3_uri, video_id),   # Job C: ~3 min
    )
    return {
        "embeddings":    embeddings,
        "chapters":      chapters_result["chapters"],
        "asr":           chapters_result["asr"],
        "silence_curve": audio_signals["silence"],
        "rms_curve":     audio_signals["rms"],
    }

# Called from Celery worker:
ingestion_data = asyncio.run(run_ingestion(s3_uri, mode, video_id))
```

**Output after Phase 1:**
- `embeddings[]` — Marengo visual vectors per 10-second segment
- `chapters[]` — Pegasus chapter boundaries with mode-specific labels
- `asr[]` — Word-level transcript
- `silence_curve[]`, `rms_curve[]`

### 3.3 Phase 2 — Boundary Scoring

**Goal:** Score every candidate timestamp with a single composite score. No dynamic programming, no multi-tier NMS — just a weighted sum above a threshold.

**Theoretical basis:** The weighted linear combination of multimodal signals is validated by Beserra & Goularte (MTA 2023) who showed no statistically significant accuracy difference between weighted-sum fusion and complex learned operators for temporal video scene segmentation. The individual signals draw from the BMN/ActionFormer temporal detection lineage (Lin et al., ICCV 2019; Zhang et al., ECCV 2022) and Event Segmentation Theory (Zacks et al., Trends in Cognitive Sciences, 2007).

**Candidate timestamps:** Every Pegasus chapter boundary + every timestamp where `rms_curve` drops below 20th percentile (silence candidate). Typically 20–50 candidates for a 60-min video.

**The scoring function:**

```python
def boundary_score(t, embeddings, chapters, silence_curve, rms_curve, mode):
    # Signal 1: Visual semantic shift (Marengo cosine distance)
    emb_before = embedding_at(t - 5, embeddings)
    emb_after  = embedding_at(t + 5, embeddings)
    visual = 1.0 - cosine_similarity(emb_before, emb_after)  # 0=same, 1=different

    # Signal 2: Audio silence at this point
    silence = min(silence_curve[t], 3.0) / 3.0  # cap at 3s, normalize to [0,1]

    # Signal 3: Pegasus semantic boundary strength
    chapter = chapter_score_at(t, chapters)  # 0.0 if not a chapter boundary,
                                              # ad_suitability/5 or 1.0 if chapter

    # Mode-specific weights
    w = WEIGHTS[mode]
    return w["visual"] * visual + w["silence"] * silence + w["semantic"] * chapter

WEIGHTS = {
    "ad_break":   {"visual": 0.25, "silence": 0.40, "semantic": 0.35},
    "news":       {"visual": 0.30, "silence": 0.10, "semantic": 0.60},
    "structural": {"visual": 0.35, "silence": 0.15, "semantic": 0.50},
}
```

**Threshold selection:** Candidates with `Score(t) > θ` are promoted. θ is set per mode:

| Mode | θ | Rationale |
|---|---|---|
| Ad-break | 0.45 | Permissive — we need 5–7 candidates from which to pick K |
| News | 0.50 | Topic shifts are strong signals; noise is lower |
| Structural | 0.40 | Act structure may have subtle signals in episodic content |

Typically yields 15–35 scored candidates above threshold.

**Output:** `candidates[]` — each with `{timestamp, score, visual, silence, semantic}`.

### 3.4 Phase 3 — Top-K Selection with Spacing Constraint

**Goal:** Pick the K best non-overlapping breaks.

This replaces the full Dynamic Programming optimizer from PRD v2.0. For K < 10 and N < 50 candidates, a greedy spacing-aware selector gives equivalent results in microseconds:

```python
def select_top_k(candidates: list, K: int, min_gap_sec: float) -> list:
    """
    Sort by score descending. Greedily select candidates that are at least
    min_gap_sec apart from all already-selected breaks.
    O(N*K) — for N=35, K=7: trivially fast.
    """
    candidates_sorted = sorted(candidates, key=lambda c: c["score"], reverse=True)
    selected = []
    for c in candidates_sorted:
        if len(selected) >= K:
            break
        if all(abs(c["timestamp"] - s["timestamp"]) >= min_gap_sec for s in selected):
            selected.append(c)
    return sorted(selected, key=lambda c: c["timestamp"])

# Default parameters by mode:
SELECTION_PARAMS = {
    "ad_break":   {"K": 6,    "min_gap_sec": 480},   # 8 min
    "news":       {"K": None, "min_gap_sec": 60},     # all above threshold, 1 min gap
    "structural": {"K": 5,    "min_gap_sec": 300},    # 5 min
}
```

**Pegasus rationale enrichment:** For each selected break, fetch the Pegasus caption for the 2 shots before and 2 shots after. Construct the `description` field:

```python
def build_description(break_t, chapters, mode):
    # Find the chapter this break belongs to from Pegasus output
    chapter_before = chapter_containing(break_t - 5, chapters)
    chapter_after  = chapter_containing(break_t + 5, chapters)
    if chapter_before and chapter_after:
        return f"{chapter_before['label']} → {chapter_after['label']}"
    return chapters[nearest_chapter_idx(break_t)].get("label", "Scene boundary")
```

**Output per selected break — strict challenge format:**

```json
{
  "start": 751.3,
  "end": 751.3,
  "type": "ad_break",
  "confidence": 0.91,
  "description": "Timeout called → Play resumes — 0.8s silence, visual shift 0.74"
}
```

For segments between breaks, a parallel pass builds the segment entries (`start < end`). The final `results[]` list is chronologically ordered segments and breaks interleaved.

---

## 4. System Architecture

### 4.1 Backend

```
┌──────────────────────────────────────────────────┐
│  FastAPI  (Baseten Truss)                        │
│                                                  │
│  POST /videos         → upload + start pipeline  │
│  GET  /videos/:id     → status + results         │
│  POST /videos/:id/optimize  → re-run Phase 3     │
│  GET  /videos/:id/export    → JSON/XML/EDL       │
│  POST /videos/:id/breaks/:bid/generate-transition │
│  GET  /videos/:id/breaks/:bid/filmstrip          │
│  WS   /ws/videos/:id/progress                   │
│                                                  │
│  Celery worker (pipeline phases)                 │
│  Redis (queue + WebSocket pub/sub)               │
└──────────────────────────────────────────────────┘
        │                    │
   AWS Bedrock          S3 + DynamoDB
   (Marengo + Pegasus)  (video + results)
```

### 4.2 Processing Sequence

```
Upload → S3                              < 1 min (parallel with below)
  ├─ [A] Marengo Embed via Bedrock       ~15-25 min
  ├─ [B] Pegasus chapters+ASR (Bedrock)  ~15-25 min (parallel with A)
  └─ [C] librosa audio signals           ~3 min (parallel)
                   │
Phase 2: boundary_score() for all candidates    < 1s
Phase 3: select_top_k() + description build     < 1s + ~5 Pegasus calls
                   │
Results → WebSocket → UI
Total wall clock: ~20-35 min for 60-min video
```

### 4.3 Technology Stack

| Component | Technology |
|---|---|
| Video understanding (required) | Marengo Embed 3.0 via AWS Bedrock |
| Video reasoning (required) | Pegasus 1.2 via AWS Bedrock |
| Audio signals | ffmpeg + librosa |
| Shot-level embeddings | Marengo (same model — embeddings pre-computed in Phase 1) |
| API + task queue | FastAPI + Celery + Redis |
| Storage | S3 (video), DynamoDB (results), S3 Vectors (embeddings) |
| Deployment (recommended) | Baseten (backend), Vercel (frontend) |
| Post-segmentation (recommended) | LTX Video — transition bumper generation |
| Frontend | Next.js 14 + React |

### 4.4 Bedrock Integration

Authentication: IAM role on the Baseten instance — no hardcoded keys.

```python
import boto3
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1",
    config=Config(retries={"max_attempts": 3, "mode": "adaptive"},
                  read_timeout=300))
```

Two bulk calls at ingestion (Marengo + Pegasus) run concurrently via `asyncio.gather()`. Per-break description enrichment calls (~5 Pegasus calls at Phase 3) are the only per-boundary LLM calls. Total Pegasus calls per video: **~7–12** (vs. ~50 naive).

Error handling: `ThrottlingException` → adaptive retry (built-in). `ModelTimeoutException` → retry with shorter segment. `ValidationException` → log and skip candidate (treat as zero semantic score).

---

## 5. Export Schema

Every submission item must have exactly these 5 fields. Flat `results[]` list, chronological order, segments and breaks interleaved.

```json
{
  "video_id": "abc-123",
  "duration": 3600.0,
  "content_type": "sports",
  "mode": "ad_break",
  "results": [
    {
      "start": 0.0,
      "end": 751.3,
      "type": "opening",
      "confidence": 0.94,
      "description": "Pre-game coverage and team introductions"
    },
    {
      "start": 751.3,
      "end": 751.3,
      "type": "ad_break",
      "confidence": 0.91,
      "description": "Timeout called → Play resumes — 0.8s silence, visual shift 0.74"
    },
    {
      "start": 751.3,
      "end": 1455.0,
      "type": "act",
      "confidence": 0.88,
      "description": "First quarter continued through second quarter opening"
    }
  ]
}
```

**Type values by mode:**

| Mode | Segment types | Break types |
|---|---|---|
| ad_break | `opening`, `act`, `credits` | `ad_break` |
| news | `story`, `field_report`, `anchor_toss` | `ad_break` |
| structural | `opening`, `act`, `transition`, `credits` | `ad_break` |

**XML export** mirrors the JSON structure:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<segmentation video_id="abc-123" duration="3600.0" content_type="sports" mode="ad_break">
  <results>
    <result>
      <start>751.3</start>
      <end>751.3</end>
      <type>ad_break</type>
      <confidence>0.91</confidence>
      <description>Timeout called → Play resumes — 0.8s silence, visual shift 0.74</description>
    </result>
  </results>
</segmentation>
```

---

## 6. Frontend — Next.js Editor Review Interface

The UI is a **Next.js 14** application with `react-player` for bi-directional video control. The challenge evaluates an "Editor review interface" — which requires genuine two-way state between the video player and the review controls. A Streamlit re-run on every input resets the video player, making the nudge/accept/reject workflow unusable. Next.js + Zustand state management resolves this.

### 6.1 Layout — Two Panels

```
┌────────────────────────┬─────────────────────────────────────────┐
│  VIDEO PLAYER          │  EDITOR REVIEW PANEL                    │
│  react-player          │                                         │
│  seekTo() on any click │  Mode: [Ad-Break ▼]                     │
│  No page reload        │  K breaks: [━━●━━] 6  Min gap: [8 min] │
│                        │  [Re-Analyze →]                         │
│  ┌─ Progress ────────┐ │  ─────────────────────────────────────  │
│  │ Phase 1 ████ done │ │                                         │
│  │ Phase 2 ████ done │ │  Break 1 — 12:31.3         conf: 0.91  │
│  │ Phase 3 ░░░░ ...  │ │  ┌─ Filmstrip ─────────────────────┐   │
│  └───────────────────┘ │  │  [frame t−1]  →  [frame t+1]    │   │
│                        │  └─────────────────────────────────┘   │
│                        │  Audio: ░░▓▓▓░░ ← silence gap visible  │
│                        │  Signals: silence 0.8s · visual 0.74   │
│                        │  "Timeout called → Play resumes"        │
│                        │  [✓ Accept] [✗ Reject] [↔ ±1s / ±5s]  │
│                        │  [✨ Generate Transition (LTX)]         │
│                        │                                         │
│                        │  Break 2 — 24:15.1         conf: 0.96  │
│                        │  ...                                    │
│                        │                                         │
│                        │  [+ Add Break at Playhead]              │
├────────────────────────┴─────────────────────────────────────────┤
│  SIGNAL TIMELINE (Recharts ComposedChart)                        │
│                                                                  │
│  10 ┤  ╭─╮     ╭──╮                                             │
│   5 ┤─╯  ╰────╯   ╰──── ← Pegasus semantic score (teal line)   │
│   0 ┤                                                            │
│     │  ░░▓▓▓▓░░░  ░░▓░  ← Audio RMS waveform (grey fill)       │
│     │   ●           ●   ← SegmentIQ breaks (teal, solid)        │
│     │    |    |    |    ← Fixed-interval baseline (grey dashed)  │
│                                                                  │
│  Hover SegmentIQ: "closure, silence 0.8s, score 0.91"           │
│  Hover Fixed:   ⚠ "Warning: cuts mid-sentence at tension 8.1"   │
└──────────────────────────────────────────────────────────────────┘
│  [Download JSON]  [Download XML]  [Download EDL]                 │
└──────────────────────────────────────────────────────────────────┘
```

### 6.2 Key Interactions

| Interaction | Behavior |
|---|---|
| Select mode + click Re-Analyze | Calls `/api/videos/:id/optimize` with new mode + K; results update in-place, no reload |
| Click break in review panel | `videoRef.seekTo(timestamp)` — instant, no reload |
| Click break marker on timeline | Scrolls panel to break card, seeks video |
| **Filmstrip** | Frame `t-0.5s` and `t+0.5s` displayed as static images, pre-extracted by backend |
| **Audio waveform** | `rms_curve[]` from Phase 1 rendered as grey fill under signal timeline |
| **Accept** (✓) | Zustand marks accepted (green). Locked from re-optimization. |
| **Reject** (✗) | Removed from active list. Break timestamp added to exclusion zone. Undo in collapsed accordion. |
| **Nudge** (±1s / ±5s) | Local Zustand update + `seekTo()`. No API call until persist on export. |
| **Generate Transition** (✨) | `POST /breaks/:id/generate-transition` → LTX bumper generated from Pegasus scene summaries → inline video preview in card |
| **Add manual break** (+) | Inserts break at `videoRef.getCurrentTime()`. Score computed from cached signal data. |
| Hover fixed-interval marker | Tooltip: checks if timestamp is at ASR word mid-point or tension > 6.0 → renders warning |
| Export | Downloads JSON/XML/EDL with all editor overrides merged |

### 6.3 Comparison View — Business Impact

The signal timeline renders three break sets simultaneously:

| Set | Color | Hover Tooltip |
|---|---|---|
| **SegmentIQ** | Teal `#14b8a6` solid | `"score: 0.91 · silence 0.8s · semantic shift"` |
| **Fixed-interval** | Grey `#94a3b8` dashed | `"⚠ Warning: cuts mid-sentence at tension 8.1"` |
| **Pegasus-only** | Muted blue `#60a5fa` | `"Chapter boundary, but audio energy still high"` |

The warning tooltip on fixed-interval breaks is computed dynamically: if the fixed-interval timestamp falls within 2s of an ASR word (not a paragraph break) and `rms_curve[t] > 0.6`, the tooltip fires. No manual curation needed — the algorithm proves the business case automatically.

### 6.4 LTX Video Integration

**When:** After segmentation is complete and editor has accepted at least one break.

**Workflow:**
1. Editor clicks `[✨ Generate Transition (LTX)]` on break card
2. Backend retrieves Pegasus summaries for the segment before and after the break
3. Constructs LTX prompt:
   ```
   Generate a 3-second visual bumper transitioning between:
   FROM: "{pegasus_summary_before}"
   TO:   "{pegasus_summary_after}"
   Style: broadcast quality, smooth, no text overlays.
   ```
4. Calls LTX Video API, gets back video URL
5. Frontend renders inline `<video>` player in the break card

**If LTX is unavailable or time runs out:** The `[✨ Generate Transition]` button is hidden. The rest of the product is unaffected. This is a post-process bonus, not a core dependency.

### 6.5 Technology Stack

| Component | Library |
|---|---|
| Framework | Next.js 14 (App Router, static export to Vercel) |
| Video player | `react-player` — `ref.seekTo()` for instant seek |
| Charts | Recharts `ComposedChart` — tension line + RMS area + reference lines |
| Editor state | Zustand — accepted/rejected/nudged breaks persist across renders |
| Filmstrip | Next.js `<Image>` — S3-served keyframes |
| Real-time progress | Native WebSocket hook |
| Styling | Tailwind CSS — dark broadcast-tool theme |
| API | `fetch` + `swr` — cached GET, mutation for persist |

### 6.6 Feature Implementation Specs

These four features are the difference between a prototype and a winning product. Each has a concrete implementation path.

#### 6.6.1 Filmstrip Component

**Backend:** One ffmpeg call per break, run after Phase 3 completes. Pre-cached to S3 so the UI loads instantly.

```python
# FastAPI endpoint — called after Phase 3 selects breaks
@app.get("/api/videos/{video_id}/breaks/{break_id}/filmstrip")
async def get_filmstrip(video_id: str, break_id: str):
    break_t = get_break_timestamp(video_id, break_id)
    before_key = f"filmstrips/{video_id}/{break_id}_before.jpg"
    after_key  = f"filmstrips/{video_id}/{break_id}_after.jpg"

    # Extract frames at t-0.5s and t+0.5s
    subprocess.run(["ffmpeg", "-ss", str(break_t - 0.5), "-i", local_video_path,
                    "-frames:v", "1", "-q:v", "3", f"/tmp/{break_id}_before.jpg"])
    subprocess.run(["ffmpeg", "-ss", str(break_t + 0.5), "-i", local_video_path,
                    "-frames:v", "1", "-q:v", "3", f"/tmp/{break_id}_after.jpg"])

    s3.upload_file(f"/tmp/{break_id}_before.jpg", BUCKET, before_key)
    s3.upload_file(f"/tmp/{break_id}_after.jpg",  BUCKET, after_key)

    return {
        "before_frame_url": f"https://{BUCKET}.s3.amazonaws.com/{before_key}",
        "after_frame_url":  f"https://{BUCKET}.s3.amazonaws.com/{after_key}",
    }
```

**Frontend — React component:**

```tsx
// components/FilmstripView.tsx
import Image from "next/image";

export function FilmstripView({ breakId, videoId }: { breakId: string; videoId: string }) {
  const { data } = useSWR(`/api/videos/${videoId}/breaks/${breakId}/filmstrip`);
  if (!data) return <div className="h-16 bg-slate-800 animate-pulse rounded" />;

  return (
    <div className="flex gap-2 items-center my-2">
      <Image src={data.before_frame_url} alt="Before cut" width={120} height={68}
             className="rounded border border-slate-600" />
      <span className="text-slate-400 text-xs">→</span>
      <Image src={data.after_frame_url}  alt="After cut"  width={120} height={68}
             className="rounded border border-slate-600" />
    </div>
  );
}
```

The side-by-side frames give an editor instant visual confirmation of whether the boundary is a genuine scene change or a false positive — without playing the video.

#### 6.6.2 Audio Waveform Overlay

The `rms_curve[]` from Phase 1 is already computed. Expose it from the backend and render it as a grey fill behind the semantic score line in the signal timeline.

```python
# Backend: included in the video status response
GET /api/videos/:id
→ {
    ...
    "signals": {
      "rms_curve":     [{"t": 0, "rms": 0.42}, {"t": 1, "rms": 0.31}, ...],
      "semantic_curve": [{"t": 0, "score": 0.12}, ...],
      "breaks":        [{"t": 751.3, "score": 0.91, "status": "pending"}, ...],
      "fixed_interval_breaks": [{"t": 720.0}, {"t": 1440.0}, ...]
    }
  }
```

```tsx
// components/SignalTimeline.tsx — Recharts ComposedChart
import { ComposedChart, Area, Line, ReferenceLine, Tooltip, XAxis, YAxis } from "recharts";

export function SignalTimeline({ signals, onBreakClick }) {
  const data = signals.rms_curve.map((r, i) => ({
    t: r.t,
    rms: r.rms,
    semantic: signals.semantic_curve[i]?.score ?? 0,
  }));

  return (
    <ComposedChart data={data} height={140}>
      <XAxis dataKey="t" tickFormatter={formatTime} />
      <YAxis yAxisId="rms"      domain={[0, 1]} hide />
      <YAxis yAxisId="semantic" domain={[0, 1]} />

      {/* Grey RMS fill — visual proof breaks land at silence dips */}
      <Area yAxisId="rms" dataKey="rms" fill="#475569" stroke="none" opacity={0.35} />

      {/* Teal semantic score line */}
      <Line yAxisId="semantic" dataKey="semantic" stroke="#14b8a6"
            strokeWidth={2} dot={false} />

      {/* SegmentIQ breaks — teal, tall */}
      {signals.breaks.map(b => (
        <ReferenceLine key={b.t} x={b.t} yAxisId="semantic"
          stroke={b.status === "accepted" ? "#14b8a6" : "#0d9488"}
          strokeWidth={2} onClick={() => onBreakClick(b.t)}
          label={{ value: `${b.score.toFixed(2)}`, fill: "#14b8a6", fontSize: 10 }} />
      ))}

      {/* Fixed-interval baseline — grey dashed */}
      {signals.fixed_interval_breaks.map(b => (
        <ReferenceLine key={b.t} x={b.t} yAxisId="semantic"
          stroke="#64748b" strokeDasharray="4 4" strokeWidth={1} />
      ))}

      <Tooltip content={<SignalTooltip signals={signals} />} />
    </ComposedChart>
  );
}
```

#### 6.6.3 Nudge — Instant Seek, No Page Reload

The Zustand store holds editor overrides. The nudge handler updates the store and seeks the video — no API call, no re-render of unrelated components.

```tsx
// store/editorStore.ts
import { create } from "zustand";

interface EditorStore {
  breaks: Record<string, { timestamp: number; status: "pending" | "accepted" | "rejected" }>;
  nudgeBreak: (breakId: string, deltaSec: number) => number;  // returns new timestamp
  acceptBreak: (breakId: string) => void;
  rejectBreak: (breakId: string) => void;
}

export const useEditorStore = create<EditorStore>((set, get) => ({
  breaks: {},
  nudgeBreak: (breakId, deltaSec) => {
    const current = get().breaks[breakId].timestamp;
    const newTs = Math.max(0, current + deltaSec);
    set(s => ({ breaks: { ...s.breaks, [breakId]: { ...s.breaks[breakId], timestamp: newTs } } }));
    return newTs;
  },
  acceptBreak: (breakId) =>
    set(s => ({ breaks: { ...s.breaks, [breakId]: { ...s.breaks[breakId], status: "accepted" } } })),
  rejectBreak: (breakId) =>
    set(s => ({ breaks: { ...s.breaks, [breakId]: { ...s.breaks[breakId], status: "rejected" } } })),
}));

// components/BreakCard.tsx — nudge buttons
const videoRef = useRef<ReactPlayer>(null);
const { nudgeBreak } = useEditorStore();

const handleNudge = (deltaSec: number) => {
  const newTs = nudgeBreak(breakId, deltaSec);
  videoRef.current?.seekTo(newTs, "seconds");  // instant seek — no reload
};

// In JSX:
<button onClick={() => handleNudge(-5)} className="btn-ghost text-xs">−5s</button>
<button onClick={() => handleNudge(-1)} className="btn-ghost text-xs">−1s</button>
<button onClick={() => handleNudge(+1)} className="btn-ghost text-xs">+1s</button>
<button onClick={() => handleNudge(+5)} className="btn-ghost text-xs">+5s</button>
```

The nudged timestamp is persisted to the backend only when the editor clicks Export — at that point the store state is serialized into the final `results[]` JSON.

#### 6.6.4 Dynamic Warning Tooltips (Comparison View)

The tooltip for fixed-interval baseline markers is computed at render time from the ASR transcript and the audio RMS curve. No manual labeling needed — the algorithm self-documents why fixed breaks are bad.

```tsx
// lib/tooltip.ts
export function getFixedIntervalTooltip(
  timestamp: number,
  rmsValues: number[],           // rms_curve[] from Phase 1
  asrWordTimestamps: number[],   // word-boundary timestamps from Pegasus ASR
  asrParagraphBreaks: number[]   // paragraph/topic breaks from ASR
): string {
  const rms = rmsValues[Math.round(timestamp)] ?? 0;
  const isHighEnergy = rms > 0.60;

  // Within 2s of an ASR word boundary but NOT a paragraph break = mid-sentence
  const nearWord = asrWordTimestamps.some(t => Math.abs(t - timestamp) < 2.0);
  const nearParagraph = asrParagraphBreaks.some(t => Math.abs(t - timestamp) < 2.0);
  const isMidSentence = nearWord && !nearParagraph;

  if (isMidSentence && isHighEnergy)
    return `⚠ Cuts mid-sentence during high audio energy (${rms.toFixed(2)})`;
  if (isMidSentence)
    return `⚠ Cuts mid-sentence — no topic boundary here`;
  if (isHighEnergy)
    return `⚠ Cuts during high audio energy (${rms.toFixed(2)}) — viewer engaged`;
  return `Fixed interval — no semantic signal at ${formatTime(timestamp)}`;
}

// Usage in SignalTooltip component:
if (payload[0]?.payload?.isFixedInterval) {
  const warning = getFixedIntervalTooltip(timestamp, rmsValues, asrWords, asrParagraphs);
  return (
    <div className="bg-slate-900 border border-slate-600 rounded p-2 text-xs max-w-48">
      <span className={warning.startsWith("⚠") ? "text-amber-400" : "text-slate-300"}>
        {warning}
      </span>
    </div>
  );
}
```

**Color coding in the comparison chart:**

```
SegmentIQ breaks  →  #14b8a6  (teal)      tall solid markers
Fixed-interval    →  #94a3b8  (grey)      short dashed markers  + ⚠ tooltip
Pegasus-only      →  #60a5fa  (muted blue) medium solid markers
```

The visual contrast is intentional: the grey baseline looks like noise against the teal SegmentIQ markers. The warning tooltip appears on hover and makes the business case without any narration.

---

## 7. Validation Plan

### 7.1 Metrics

| Metric | Target | Tolerance |
|---|---|---|
| Precision | ≥ 80% | Boundary within ±2s of human label = TP |
| Recall | ≥ 75% | |
| F1 | ≥ 0.77 | |
| Timing MAE | < 2.0s | |

Reported per mode (ad-break, news, structural) and overall.

### 7.2 Baselines

| Baseline | Method |
|---|---|
| Fixed-interval | Break every 12 minutes regardless of content |
| Pegasus-only | Use Pegasus chapter boundaries with no scoring |
| **SegmentIQ** | Phase 2 weighted scoring + Phase 3 Top-K |

The comparison view in the UI renders all three simultaneously — the ablation is built into the demo.

### 7.3 Error Analysis

Document per mode:
- False positives: which signal(s) drove a bad boundary? (e.g., sports replay causing visual shift false positive)
- False negatives: which signals were absent at a missed boundary?
- Failure modes: news stories with no audio silence, sports with continuous motion

---

## 8. Build Plan — 3 Days

### Day 1: Backend Ingestion + Scoring (Phases 1–2)

| Task | Hours |
|---|---|
| S3 upload + Bedrock client setup (Marengo + Pegasus) | 3h |
| Phase 1A: Marengo embedding call + S3 Vectors storage | 2h |
| Phase 1B: Pegasus chapter segmentation — 3 mode system prompts | 3h |
| Phase 1C: librosa audio RMS + ffmpeg silence detection | 2h |
| Wire `asyncio.gather()` across all 3 ingestion jobs (parallel execution) | 0.5h |
| Phase 2: `boundary_score()` — 3-signal weighted heuristic | 2h |
| FastAPI skeleton + DynamoDB schema + WebSocket progress | 1.5h |
| **Total** | **14h** |

**Exit criteria:** Upload a video → Marengo, Pegasus, and audio jobs complete concurrently. Scored candidate list available.

### Day 2: Selection + API + Core UI

| Task | Hours |
|---|---|
| Phase 3: `select_top_k()` + description enrichment (~5 Pegasus calls) | 2h |
| JSON/XML/EDL export endpoints | 1.5h |
| Filmstrip endpoint: `ffmpeg -ss {t±0.5}` per break → S3 → URL response | 1h |
| LTX transition generation endpoint | 2h |
| Next.js scaffold: Zustand `editorStore`, Tailwind dark theme, routing | 1h |
| `react-player` video panel + WebSocket progress bar | 2h |
| Break cards: filmstrip (`FilmstripView`), nudge buttons → `seekTo()`, accept/reject | 3.5h |
| **Total** | **13h** |

**Exit criteria:** Full pipeline works end-to-end for one content type. Nudge buttons seek video instantly with zero page reload. Filmstrip renders frame pair for every break.

### Day 3: UI Polish + Validation + Demo

| Task | Hours |
|---|---|
| Recharts `ComposedChart`: RMS area fill + semantic score line + break markers | 2h |
| Comparison view: 3 break sets, styled markers, `getFixedIntervalTooltip()` | 2h |
| LTX inline bumper preview in break card | 1h |
| Mode switching (ad-break / news / structural) end-to-end test | 2h |
| Process all 3 test videos, annotate ground truth, compute P/R/F1 | 3h |
| Error analysis document | 1h |
| Record 3-minute demo | 1h |
| Deploy to Baseten + Vercel | 1h |
| **Total** | **13h** |

**Exit criteria:** All 3 content types processed, P/R/F1 computed, demo recorded, app live at Vercel URL.

---

## 9. Demo Script — 3 Minutes

### 0:00–1:00 — Sports (Ad-Break Mode)

1. Upload 90-min sports video (or use pre-processed). Phase 1 completes: "Marengo embeddings + Pegasus chapters extracted."
2. Show 6 ad breaks on the signal timeline — all at silence dips and Pegasus-labeled timeouts.
3. Click Break 1 → video seeks instantly. Filmstrip shows the frame before/after the timeout cut.
4. Hover a grey fixed-interval marker → tooltip: "⚠ Cuts mid-sentence during tension 7.8."
5. **Key line:** "Every break lands at a natural pause. Three signals — visual shift, audio silence, semantic boundary — fused into a single score."

### 1:00–1:45 — News (News Mode)

1. Switch mode to **News**. Click Re-Analyze — results refresh in-place.
2. Show story boundaries with Pegasus topic labels: "Weather → Sports → Breaking News."
3. Click Export → show the JSON `{start, end, type, confidence, description}` output.
4. **Key line:** "Same pipeline. Different system prompt. Auto-adapted to news topic segmentation."

### 1:45–2:30 — Episodic (Structural Mode)

1. Switch to **Structural** mode on a pre-processed 45-min show.
2. Show cold open, act 1, act 2, credits detected automatically.
3. **Live:** Change K from 5 to 3 → re-optimize → breaks shift instantly.
4. Click `[✨ Generate Transition]` on one break → 3-second LTX bumper plays inline.
5. **Key line:** "One engine, three modes. The optimizer re-solves in milliseconds. LTX generates transitions from Pegasus scene summaries."

### 2:30–3:00 — Business Case

1. Show comparison view: SegmentIQ (teal) vs. fixed-interval (grey). Warning tooltips appear on hover.
2. Show export JSON for all three content types.
3. **Key line:** "Fixed-interval breaks lose viewers. SegmentIQ breaks land after resolution. The decision layer is what TwelveLabs doesn't ship."

---

## 10. Submission Deliverables Checklist

### Required

- [ ] Deployed application (Baseten + Vercel) processing all 3 content types
- [ ] Visual timeline with segments, confidence scores, RMS waveform, comparison baseline
- [ ] Export: JSON with `{start, end, type, confidence, description}` + XML export
- [ ] Editor review interface: filmstrip, accept/reject/nudge, add manual break
- [ ] 3-minute demo across sports, news, episodic
- [ ] Algorithm explanation: 3-phase weighted scoring with citations (Beserra & Goularte MTA 2023, Zacks et al. 2007, BMN/ActionFormer lineage)
- [ ] Feature engineering: 3 signals (visual cosine distance, audio silence, Pegasus semantic score) + mode-specific weights
- [ ] TwelveLabs + AWS Bedrock integration: Marengo embeddings + Pegasus chapter segmentation + mode system prompts
- [ ] Performance metrics: wall clock per phase, Pegasus call count (~7–12), memory (~1.5 GB peak)
- [ ] Precision/recall/F1 per content type (≥ 0.77 F1 target)
- [ ] Error analysis per content type

### Bonus

- [ ] LTX Video transition bumper generation (inline in editor panel)
- [ ] Near-real-time: < 1x content duration, WebSocket live progress
- [ ] Configurable K + min-gap per mode (already built into Phase 3)
- [ ] EDL export for editing tool integration

---

## 11. What Was Cut vs. PRD v2.0 — and Why It's Safe

| PRD v2.0 Component | Decision | Reason |
|---|---|---|
| Phase 1: Compressed-domain pre-scan (ffprobe, MV extraction) | **Cut** | Clever but ~3h of glue code. Marengo already captures visual transitions. Add back in if time allows. |
| Dynamic Programming optimizer | **Replaced with greedy Top-K** | Greedy gives equivalent results for K < 10 and N < 50. DP adds ~2h of implementation for negligible demo-quality gain. |
| 8-signal boundary potential function | **Simplified to 3 signals** | 3 signals (visual, silence, semantic) cover the principal axes. The other 5 are refinements, not foundations. |
| Separate TAD frameworks (BMN, ActionFormer, TriDet via OpenTAD) | **Cited for theory, not integrated** | TransNetV2 handles shot detection; Marengo handles embeddings. Full TAD framework integration is 1 day of work. |
| Event Segmentation Theory structured prompts (Phase 4) | **Merged into Pegasus mode prompts** | The EST disruption/closure/engagement dimensions are incorporated into the mode system prompts rather than separate calls. Saves ~10 Pegasus calls. |
| Narrative tension curve with LLM calibration (Phase 5) | **Replaced with RMS waveform** | The RMS waveform is equally persuasive visually and requires zero LLM calls. The tension curve concept survives as the Pegasus semantic score time-series. |
| Next.js UI features | **Kept in full** | Filmstrip, waveform overlay, LTX button, comparison view with warning tooltips — these are the UI differentiators. |
| Export schema (JSON/XML/EDL) | **Kept in full** | Required by challenge. Already defined. |
| Validation plan (P/R/F1, baselines, error analysis) | **Kept in full** | Required submission deliverable. |

**The core thesis is intact.** TwelveLabs = Perception. SegmentIQ = Decision. The decision layer is a 3-signal weighted scoring engine rather than a 6-phase research pipeline — but both produce the same class of output and the same differentiated value proposition.

---

## 12. References

| # | Citation | Role in MVWP |
|---|---|---|
| [1] | Zhang et al. "ActionFormer: Localizing Moments of Actions with Transformers." *ECCV*, 2022. | Theoretical basis for boundary candidate scoring |
| [2] | Lin et al. "BMN: Boundary-Matching Network for Temporal Action Proposal Generation." *ICCV*, 2019. | Boundary confidence map concept underlying Phase 2 |
| [3] | Beserra, Goularte. "Multimodal Early Fusion Operators for Temporal Video Scene Segmentation." *Multimedia Tools and Applications*, 2023. | Validates weighted linear fusion — no accuracy loss vs. complex operators |
| [4] | Zacks et al. "Event Perception: A Mind-Brain Perspective." *Trends in Cognitive Sciences*, 2007. | Theoretical basis for Pegasus mode prompts (prediction disruption, closure) |
| [5] | Soucek, Lokoc. "TransNetV2: An Effective Deep Network Architecture for Fast Shot Transition Detection." *ACM MM*, 2024. | Shot-level granularity understanding (theory; Marengo replaces in implementation) |
| [6] | Reagan et al. "The Emotional Arcs of Stories are Dominated by Six Basic Shapes." *EPJ Data Science*, 2016. | Narrative arc concept behind RMS waveform as tension proxy |
| [7] | Mun et al. "BaSSL: Boundary-aware Self-Supervised Learning for Video Scene Segmentation." *ACCV*, 2022. | Scene grouping concept (Marengo cosine similarity replaces in implementation) |
