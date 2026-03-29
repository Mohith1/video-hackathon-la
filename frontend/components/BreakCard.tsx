"use client";
import { useRef, useState } from "react";
import { useEditorStore } from "@/store/editorStore";
import FilmstripView from "./FilmstripView";
import { formatTime } from "@/lib/utils";
import { generateTransition } from "@/lib/api";

interface Props {
  breakId: string;
  videoId: string;
  playerRef: React.RefObject<any>;
}

export default function BreakCard({ breakId, videoId, playerRef }: Props) {
  const { breaks, nudgeBreak, acceptBreak, rejectBreak, restoreBreak } = useEditorStore();
  const b = breaks[breakId];
  const [ltxLoading, setLtxLoading] = useState(false);
  const [ltxPrompt, setLtxPrompt] = useState<string | null>(null);

  if (!b) return null;

  const handleSeek = () => {
    playerRef.current?.seekTo(b.timestamp, "seconds");
  };

  const handleNudge = (deltaSec: number) => {
    const newTs = nudgeBreak(breakId, deltaSec);
    playerRef.current?.seekTo(newTs, "seconds");
  };

  const handleGenerateTransition = async () => {
    setLtxLoading(true);
    const result = await generateTransition(videoId, breakId);
    if (result?.prompt) setLtxPrompt(result.prompt);
    setLtxLoading(false);
  };

  const statusColors = {
    pending: "border-slate-700 bg-slate-800",
    accepted: "border-emerald-600/50 bg-emerald-900/10",
    rejected: "border-slate-800 bg-slate-900/50 opacity-50",
  };

  return (
    <div className={`rounded-lg border p-3 transition-all ${statusColors[b.status]}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <button
          onClick={handleSeek}
          className="text-teal-400 font-mono text-sm hover:text-teal-300 transition-colors font-medium"
        >
          {formatTime(b.timestamp)}
        </button>
        <div className="flex items-center gap-2">
          <span className="text-slate-500 text-xs">conf:</span>
          <span
            className={`text-xs font-mono font-medium ${
              b.score > 0.8 ? "text-emerald-400" : b.score > 0.6 ? "text-teal-400" : "text-slate-400"
            }`}
          >
            {b.score.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Filmstrip */}
      <FilmstripView videoId={videoId} breakId={breakId} />

      {/* Signal details */}
      <div className="text-xs text-slate-500 space-y-0.5 mb-2">
        <div className="flex gap-3">
          <span>silence <span className="text-slate-300">{(b.silence * 3).toFixed(1)}s</span></span>
          <span>visual <span className="text-slate-300">{b.visual.toFixed(2)}</span></span>
          <span>semantic <span className="text-slate-300">{b.semantic.toFixed(2)}</span></span>
        </div>
        {b.description && (
          <div className="text-slate-400 text-xs truncate" title={b.description}>
            "{b.description}"
          </div>
        )}
      </div>

      {/* Nudge buttons */}
      {b.status !== "rejected" && (
        <div className="flex gap-1 flex-wrap mb-2">
          <button onClick={() => handleNudge(-5)} className="btn-ghost">−5s</button>
          <button onClick={() => handleNudge(-1)} className="btn-ghost">−1s</button>
          <button onClick={() => handleNudge(+1)} className="btn-ghost">+1s</button>
          <button onClick={() => handleNudge(+5)} className="btn-ghost">+5s</button>
        </div>
      )}

      {/* Accept/Reject */}
      <div className="flex gap-2">
        {b.status === "rejected" ? (
          <button onClick={() => restoreBreak(breakId)} className="btn-ghost text-xs">
            Undo Reject
          </button>
        ) : (
          <>
            <button
              onClick={() => acceptBreak(breakId)}
              className={`btn-success ${b.status === "accepted" ? "opacity-100" : ""}`}
            >
              {b.status === "accepted" ? "✓ Accepted" : "✓ Accept"}
            </button>
            <button onClick={() => rejectBreak(breakId)} className="btn-danger">
              ✗ Reject
            </button>
            <button
              onClick={handleGenerateTransition}
              disabled={ltxLoading}
              className="btn-ghost flex-1 text-center"
              title="Generate LTX transition"
            >
              {ltxLoading ? "..." : "✨ Transition"}
            </button>
          </>
        )}
      </div>

      {/* LTX prompt preview */}
      {ltxPrompt && (
        <div className="mt-2 p-2 bg-slate-900 rounded text-xs text-slate-400 border border-slate-700">
          <span className="text-slate-600">LTX prompt: </span>{ltxPrompt}
        </div>
      )}
    </div>
  );
}
