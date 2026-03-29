# SegmentIQ

AI-powered video segmentation · TwelveLabs Marengo + Pegasus via AWS Bedrock · Challenge Track 2

---

## Quick Start

### 1. Set AWS credentials

```bash
# Edit backend/.env
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
S3_BUCKET=your-bucket-name
S3_VECTORS_BUCKET=your-embeddings-bucket
DYNAMODB_TABLE=segmentiq-videos
```

### 2. Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Start Redis (required)
docker run -d -p 6379:6379 redis:7-alpine

# Start API server
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

### Docker (all-in-one)

```bash
docker-compose up --build
# App: http://localhost:3000   API: http://localhost:8000
```

---

## Architecture

```
VIDEO UPLOAD (MP4/MOV/MKV)
         │
  PHASE 1 — asyncio.gather() — wall clock = max(A,B,C)
  ├─ A: Marengo Embed 3.0 via Bedrock  ~15-25 min
  ├─ B: Pegasus 1.2 chapters+ASR via Bedrock
  └─ C: librosa RMS + ffmpeg silence   ~3 min
         │
  PHASE 2 — Boundary Scoring (<1s)
  Score(t) = w1·visual + w2·silence + w3·semantic
         │
  PHASE 3 — Top-K Selection + Pegasus enrichment (<1s + ~5 calls)
         │
  Editor Review UI → Export JSON / XML / EDL
```

## Three Modes

| Mode | Content | Target Breaks |
|---|---|---|
| **Ad-Break** | Sports broadcast | 5–7 natural pauses |
| **News** | News program | Topic/story boundaries |
| **Structural** | Episodic content | Cold open, acts, credits |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/videos` | Upload video + start pipeline |
| GET | `/api/videos/:id` | Status + results + signals |
| POST | `/api/videos/:id/optimize` | Re-run Phase 3 (new mode/K) |
| GET | `/api/videos/:id/export?format=json\|xml\|edl` | Export results |
| GET | `/api/videos/:id/breaks/:bid/filmstrip` | Before/after frames |
| POST | `/api/videos/:id/breaks/:bid/generate-transition` | LTX bumper |
| WS | `/ws/videos/:id/progress` | Real-time pipeline progress |

## AWS Resources Needed

1. **S3 Bucket** — video storage + filmstrip frames
2. **S3 Bucket** — Marengo embedding vectors
3. **DynamoDB Table** — auto-created on startup
4. **Bedrock Models** enabled in us-east-1:
   - `twelvelabs.marengo-embed-3-0`
   - `twelvelabs.pegasus-1-2`

## Export Schema

```json
{
  "video_id": "abc-123",
  "duration": 3600.0,
  "content_type": "sports",
  "mode": "ad_break",
  "results": [
    { "start": 0.0,   "end": 751.3, "type": "opening",  "confidence": 0.94, "description": "Pre-game coverage" },
    { "start": 751.3, "end": 751.3, "type": "ad_break", "confidence": 0.91, "description": "Timeout called -> Play resumes" }
  ]
}
```
