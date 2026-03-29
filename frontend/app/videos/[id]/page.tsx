"use client";
import { useEffect, useRef, useState, Component, ReactNode } from "react";
import useSWR from "swr";
import { getVideo, optimizeVideo, createWebSocket } from "@/lib/api";
import { useEditorStore } from "@/store/editorStore";
import VideoPlayer from "@/components/VideoPlayer";
import BreakCard from "@/components/BreakCard";
import SignalTimeline from "@/components/SignalTimeline";
import ProgressBar from "@/components/ProgressBar";
import ExportButtons from "@/components/ExportButtons";
import { formatTime } from "@/lib/utils";

class ErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null };
  static getDerivedStateFromError(e: Error) { return { error: e.message }; }
  render() {
    if (this.state.error) return (
      <div className="h-screen flex items-center justify-center text-center p-8">
        <div>
          <div className="text-red-400 text-sm mb-2">Page error</div>
          <div className="text-slate-500 text-xs font-mono">{this.state.error}</div>
          <button onClick={() => window.location.reload()} className="mt-4 px-4 py-2 bg-slate-700 text-slate-300 rounded text-sm hover:bg-slate-600">Reload</button>
        </div>
      </div>
    );
    return this.props.children;
  }
}

const MODES = [
  { value: "ad_break", label: "Ad-Break" },
  { value: "news", label: "News" },
  { value: "structural", label: "Structural" },
];


interface PageProps {
  params: { id: string };
}

function VideoPageInner({ params }: PageProps) {
  const { id: videoId } = params;
  const playerRef = useRef<any>(null);
  const [wsStatus, setWsStatus] = useState<{ status: string; progress: number }>({
    status: "pending",
    progress: 0,
  });
  const [reanalyzing, setReanalyzing] = useState(false);

  const { data: video, mutate } = useSWR(
    videoId ? `video-${videoId}` : null,
    () => getVideo(videoId),
    { refreshInterval: wsStatus.status !== "complete" && wsStatus.status !== "failed" ? 3000 : 0 }
  );

  const { setVideoData, breaks, mode, setMode, k, setK, minGapSec, setMinGapSec } =
    useEditorStore();

  // WebSocket progress (falls back to polling via SWR if WS fails)
  useEffect(() => {
    if (!videoId) return;
    let ws: WebSocket | null = null;
    try {
      ws = createWebSocket(videoId);
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          setWsStatus({ status: msg.status, progress: msg.progress ?? 0 });
          if (msg.status === "complete" || msg.status === "failed") {
            mutate();
            ws?.close();
          }
        } catch {}
      };
      ws.onerror = () => { try { ws?.close(); } catch {} };
    } catch (e) {
      // WebSocket not available — SWR polling handles status updates
    }
    return () => { try { ws?.close(); } catch {} };
  }, [videoId, mutate]);

  // Sync store when video data loads
  useEffect(() => {
    if (!video || video.status !== "complete") return;
    const sigBreaks = video.signals?.breaks ?? [];
    setVideoData(
      videoId,
      sigBreaks.map((b: any) => ({
        timestamp: b.t,
        score: b.score,
        status: b.status ?? "pending",
        visual: b.visual ?? 0,
        silence: b.silence ?? 0,
        semantic: b.semantic ?? 0,
        description: undefined,
      })),
      video.mode,
      video.duration ?? 3600
    );
    setMode(video.mode);
    setWsStatus({ status: "complete", progress: 100 });
  }, [video?.status, video?.video_id]);

  const handleReanalyze = async () => {
    setReanalyzing(true);
    try {
      await optimizeVideo(videoId, mode, k || undefined, minGapSec || undefined);
      await mutate();
    } catch (e) {
      console.error(e);
    } finally {
      setReanalyzing(false);
    }
  };

  const handleBreakClick = (t: number) => {
    playerRef.current?.seekTo(t, "seconds");
  };

  const currentStatus = video?.status ?? wsStatus.status;
  const isComplete = currentStatus === "complete";

  const inputCls = "w-full rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-teal-500 border transition-colors";
  const inputStyle = { backgroundColor: "var(--bg-subtle)", borderColor: "var(--border)", color: "var(--text)" };

  return (
    <div className="h-[calc(100vh-53px)] flex flex-col overflow-hidden" style={{ backgroundColor: "var(--bg)" }}>
      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Video player */}
        <div className="flex-1 flex flex-col p-4 gap-3 min-w-0">
          <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-3)" }}>
            <span className="font-mono" style={{ color: "var(--text-2)" }}>{videoId.slice(0, 8)}...</span>
            <span className={`px-2 py-0.5 rounded-full text-xs ${
                isComplete ? "bg-emerald-500/15 text-emerald-500"
                : currentStatus === "failed" ? "bg-red-500/15 text-red-400"
                : "text-teal-400"}`}
              style={!isComplete && currentStatus !== "failed" ? { backgroundColor: "var(--bg-subtle)" } : {}}>
              {currentStatus}
            </span>
            {video?.duration && <span>· {formatTime(video.duration)}</span>}
            {video?.processing_time_sec && (
              <span>· {video.processing_time_sec}s
                {video.realtime_ratio && <span className="text-teal-500"> ({video.realtime_ratio}x)</span>}
              </span>
            )}
          </div>

          {video?.video_url ? (
            <VideoPlayer url={video.video_url} playerRef={playerRef} />
          ) : isComplete ? (
            <div className="aspect-video rounded-xl border flex flex-col items-center justify-center gap-3"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-card)" }}>
              <div className="text-sm" style={{ color: "var(--text-2)" }}>Video preview unavailable</div>
              <div className="text-xs text-center max-w-xs leading-relaxed" style={{ color: "var(--text-3)" }}>
                S3-imported videos require signed credentials for playback.
                All segmentation results and exports are fully functional.
              </div>
            </div>
          ) : (
            <div className="aspect-video rounded-xl border flex items-center justify-center"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-card)" }}>
              <div className="text-sm" style={{ color: "var(--text-3)" }}>Processing...</div>
            </div>
          )}

          {!isComplete && <ProgressBar status={wsStatus.status} progress={wsStatus.progress} />}
        </div>

        {/* Right: Editor panel */}
        <div className="w-80 flex flex-col border-l overflow-hidden" style={{ borderColor: "var(--border)" }}>
          {/* Controls */}
          <div className="p-4 border-b space-y-3 flex-shrink-0" style={{ borderColor: "var(--border)" }}>
            <div className="space-y-1">
              <label className="text-xs" style={{ color: "var(--text-3)" }}>Mode</label>
              <select value={mode} onChange={(e) => setMode(e.target.value)}
                className={inputCls} style={inputStyle}>
                {MODES.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-xs" style={{ color: "var(--text-3)" }}>K breaks</label>
                <input type="number" min={1} max={20} value={k}
                  onChange={(e) => setK(Number(e.target.value))}
                  className={inputCls} style={inputStyle} />
              </div>
              <div className="space-y-1">
                <label className="text-xs" style={{ color: "var(--text-3)" }}>Min gap (s)</label>
                <input type="number" min={30} max={3600} step={30} value={minGapSec}
                  onChange={(e) => setMinGapSec(Number(e.target.value))}
                  className={inputCls} style={inputStyle} />
              </div>
            </div>

            <button onClick={handleReanalyze} disabled={!isComplete || reanalyzing}
              className={`w-full py-2 rounded text-sm font-medium transition-all ${
                isComplete && !reanalyzing ? "bg-teal-500 hover:bg-teal-600 text-white" : "cursor-not-allowed"
              }`}
              style={!isComplete || reanalyzing ? { backgroundColor: "var(--bg-subtle)", color: "var(--text-3)" } : {}}>
              {reanalyzing ? "Re-analyzing..." : "Re-Analyze →"}
            </button>
          </div>

          {/* Break cards */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {isComplete ? (
              Object.keys(breaks).length > 0 ? (
                <>
                  <div className="text-xs px-1" style={{ color: "var(--text-3)" }}>
                    {Object.values(breaks).filter((b) => b.status !== "rejected").length} breaks
                    {" · "}
                    {Object.values(breaks).filter((b) => b.status === "accepted").length} accepted
                  </div>
                  {Object.keys(breaks).map((id) => (
                    <BreakCard key={id} breakId={id} videoId={videoId} playerRef={playerRef} />
                  ))}
                </>
              ) : (
                <div className="text-xs text-center py-8" style={{ color: "var(--text-3)" }}>
                  No breaks found. Try lowering K or adjusting the threshold.
                </div>
              )
            ) : (
              <div className="text-xs text-center py-8" style={{ color: "var(--text-3)" }}>Processing...</div>
            )}
          </div>

          {/* Export */}
          {isComplete && (
            <div className="p-3 border-t flex flex-col gap-2" style={{ borderColor: "var(--border)" }}>
              <div className="text-xs" style={{ color: "var(--text-3)" }}>Export</div>
              <ExportButtons videoId={videoId} />
            </div>
          )}
        </div>
      </div>

      {/* Bottom: Signal timeline */}
      {isComplete && video?.signals && (
        <div className="border-t p-3" style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-card)" }}>
          <div className="text-xs mb-2 flex items-center gap-4" style={{ color: "var(--text-3)" }}>
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-teal-500 inline-block"></span>
              SegmentIQ
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-0.5 bg-slate-500 border-dashed border-t inline-block"></span>
              Fixed-interval
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-2 bg-slate-500/35 inline-block"></span>
              Audio RMS
            </span>
          </div>
          <SignalTimeline
            signals={video.signals}
            duration={video.duration ?? 3600}
            onBreakClick={handleBreakClick}
          />
        </div>
      )}
    </div>
  );
}

export default function VideoPage({ params }: PageProps) {
  return (
    <ErrorBoundary>
      <VideoPageInner params={params} />
    </ErrorBoundary>
  );
}
