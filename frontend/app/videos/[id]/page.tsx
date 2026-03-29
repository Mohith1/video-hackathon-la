"use client";
import { useEffect, useRef, useState, use } from "react";
import useSWR from "swr";
import { getVideo, optimizeVideo, createWebSocket } from "@/lib/api";
import { useEditorStore } from "@/store/editorStore";
import VideoPlayer from "@/components/VideoPlayer";
import BreakCard from "@/components/BreakCard";
import SignalTimeline from "@/components/SignalTimeline";
import ProgressBar from "@/components/ProgressBar";
import ExportButtons from "@/components/ExportButtons";
import { formatTime } from "@/lib/utils";

const MODES = [
  { value: "ad_break", label: "Ad-Break" },
  { value: "news", label: "News" },
  { value: "structural", label: "Structural" },
];

const MODE_K_DEFAULTS: Record<string, number> = {
  ad_break: 6,
  news: 8,
  structural: 5,
};

const MODE_GAP_DEFAULTS: Record<string, number> = {
  ad_break: 480,
  news: 60,
  structural: 300,
};

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function VideoPage({ params }: PageProps) {
  const { id: videoId } = use(params);
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

  const { setVideoData, breaks, mode, setMode, k, setK, minGapSec, setMinGapSec, duration } =
    useEditorStore();

  // WebSocket progress
  useEffect(() => {
    if (!videoId) return;
    const ws = createWebSocket(videoId);
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      setWsStatus({ status: msg.status, progress: msg.progress ?? 0 });
      if (msg.status === "complete" || msg.status === "failed") {
        mutate();
        ws.close();
      }
    };
    ws.onerror = () => ws.close();
    return () => ws.close();
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

  return (
    <div className="h-[calc(100vh-53px)] flex flex-col overflow-hidden">
      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Video player */}
        <div className="flex-1 flex flex-col p-4 gap-3 min-w-0">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="font-mono text-slate-400">{videoId.slice(0, 8)}...</span>
            <span
              className={`px-2 py-0.5 rounded-full text-xs ${
                isComplete
                  ? "bg-emerald-900/50 text-emerald-400"
                  : currentStatus === "failed"
                  ? "bg-red-900/50 text-red-400"
                  : "bg-slate-700 text-slate-400"
              }`}
            >
              {currentStatus}
            </span>
            {video?.duration && (
              <span className="text-slate-600">· {formatTime(video.duration)}</span>
            )}
          </div>

          {video?.video_url ? (
            <VideoPlayer url={video.video_url} playerRef={playerRef} />
          ) : (
            <div className="aspect-video bg-slate-800 rounded-lg flex items-center justify-center">
              <div className="text-slate-600 text-sm">Video loading...</div>
            </div>
          )}

          {!isComplete && (
            <ProgressBar
              status={wsStatus.status}
              progress={wsStatus.progress}
            />
          )}
        </div>

        {/* Right: Editor panel */}
        <div className="w-80 flex flex-col border-l border-slate-800 overflow-hidden">
          {/* Controls */}
          <div className="p-4 border-b border-slate-800 space-y-3 flex-shrink-0">
            {/* Mode selector */}
            <div className="space-y-1">
              <label className="text-xs text-slate-500">Mode</label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-300 focus:outline-none focus:border-teal-500"
              >
                {MODES.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>

            {/* K and min gap */}
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-xs text-slate-500">K breaks</label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={k}
                  onChange={(e) => setK(Number(e.target.value))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-300 focus:outline-none focus:border-teal-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-500">Min gap (s)</label>
                <input
                  type="number"
                  min={30}
                  max={3600}
                  step={30}
                  value={minGapSec}
                  onChange={(e) => setMinGapSec(Number(e.target.value))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-sm text-slate-300 focus:outline-none focus:border-teal-500"
                />
              </div>
            </div>

            <button
              onClick={handleReanalyze}
              disabled={!isComplete || reanalyzing}
              className={`w-full py-2 rounded text-sm font-medium transition-all ${
                isComplete && !reanalyzing
                  ? "bg-teal-500 hover:bg-teal-600 text-white"
                  : "bg-slate-700 text-slate-500 cursor-not-allowed"
              }`}
            >
              {reanalyzing ? "Re-analyzing..." : "Re-Analyze →"}
            </button>
          </div>

          {/* Break cards */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {isComplete ? (
              Object.keys(breaks).length > 0 ? (
                <>
                  <div className="text-xs text-slate-500 px-1">
                    {Object.values(breaks).filter((b) => b.status !== "rejected").length} breaks
                    {" · "}
                    {Object.values(breaks).filter((b) => b.status === "accepted").length} accepted
                  </div>
                  {Object.keys(breaks).map((id) => (
                    <BreakCard
                      key={id}
                      breakId={id}
                      videoId={videoId}
                      playerRef={playerRef}
                    />
                  ))}
                </>
              ) : (
                <div className="text-slate-600 text-xs text-center py-8">
                  No breaks found. Try lowering K or adjusting the threshold.
                </div>
              )
            ) : (
              <div className="text-slate-600 text-xs text-center py-8">
                Processing...
              </div>
            )}
          </div>

          {/* Export */}
          {isComplete && (
            <div className="p-3 border-t border-slate-800 flex flex-col gap-2">
              <div className="text-xs text-slate-500">Export</div>
              <ExportButtons videoId={videoId} />
            </div>
          )}
        </div>
      </div>

      {/* Bottom: Signal timeline */}
      {isComplete && video?.signals && (
        <div className="border-t border-slate-800 p-3 bg-slate-900/50">
          <div className="text-xs text-slate-500 mb-2 flex items-center gap-4">
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
