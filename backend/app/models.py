from pydantic import BaseModel
from typing import Optional, List, Literal
from enum import Enum

class ProcessingMode(str, Enum):
    AD_BREAK = "ad_break"
    NEWS = "news"
    STRUCTURAL = "structural"

class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PHASE1 = "phase1"
    PHASE2 = "phase2"
    PHASE3 = "phase3"
    COMPLETE = "complete"
    FAILED = "failed"

class BreakStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class SegmentResult(BaseModel):
    start: float
    end: float
    type: str
    confidence: float
    description: str

class RMSPoint(BaseModel):
    t: float
    rms: float

class SemanticPoint(BaseModel):
    t: float
    score: float

class BreakSignal(BaseModel):
    t: float
    score: float
    status: BreakStatus = BreakStatus.PENDING
    visual: float = 0.0
    silence: float = 0.0
    semantic: float = 0.0

class FixedIntervalBreak(BaseModel):
    t: float

class Signals(BaseModel):
    rms_curve: List[RMSPoint] = []
    semantic_curve: List[SemanticPoint] = []
    breaks: List[BreakSignal] = []
    fixed_interval_breaks: List[FixedIntervalBreak] = []

class VideoStatus(BaseModel):
    video_id: str
    status: ProcessingStatus
    mode: ProcessingMode
    progress: int = 0  # 0-100
    duration: Optional[float] = None
    content_type: Optional[str] = None
    results: List[SegmentResult] = []
    signals: Optional[Signals] = None
    error: Optional[str] = None
    s3_uri: Optional[str] = None

class UploadResponse(BaseModel):
    video_id: str
    upload_url: str
    status: str = "pending"

class OptimizeRequest(BaseModel):
    mode: ProcessingMode
    k: Optional[int] = None
    min_gap_sec: Optional[float] = None

class NudgeRequest(BaseModel):
    break_id: str
    delta_sec: float

class ExportFormat(str, Enum):
    JSON = "json"
    XML = "xml"
    EDL = "edl"
