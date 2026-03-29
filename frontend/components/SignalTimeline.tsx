"use client";
import {
  ComposedChart,
  Area,
  Line,
  ReferenceLine,
  Tooltip,
  XAxis,
  YAxis,
  ResponsiveContainer,
} from "recharts";
import { formatTime } from "@/lib/utils";
import { getFixedIntervalTooltip } from "@/lib/tooltip";
import { useEditorStore } from "@/store/editorStore";

interface Props {
  signals: {
    rms_curve: { t: number; rms: number }[];
    semantic_curve: { t: number; score: number }[];
    breaks: { t: number; score: number; status: string }[];
    fixed_interval_breaks: { t: number }[];
  };
  duration: number;
  onBreakClick: (t: number) => void;
}

const CustomTooltip = ({ active, payload, label, signals }: any) => {
  if (!active || !payload?.length) return null;
  const rms = payload.find((p: any) => p.dataKey === "rms")?.value ?? 0;
  const semantic = payload.find((p: any) => p.dataKey === "semantic")?.value ?? 0;

  return (
    <div className="bg-slate-900 border border-slate-700 rounded p-2 text-xs max-w-48">
      <div className="text-slate-400 mb-1">{formatTime(label)}</div>
      <div className="text-teal-400">semantic: {semantic.toFixed(3)}</div>
      <div className="text-slate-400">RMS: {rms.toFixed(3)}</div>
    </div>
  );
};

export default function SignalTimeline({ signals, duration, onBreakClick }: Props) {
  const { breaks: editorBreaks } = useEditorStore();

  // Downsample data for performance (max 1000 points)
  const rms = signals.rms_curve || [];
  const semantic = signals.semantic_curve || [];
  const step = Math.max(1, Math.floor(rms.length / 1000));

  const data = rms
    .filter((_, i) => i % step === 0)
    .map((r, i) => ({
      t: r.t,
      rms: r.rms,
      semantic: semantic[i * step]?.score ?? 0,
    }));

  const asrWords = signals.breaks.map((b) => b.t); // approximate
  const asrParagraphs = signals.breaks.map((b) => b.t);
  const rmsValues = rms.map((r) => r.rms);

  // Sync editor break statuses
  const activeBreaks = signals.breaks.map((b, i) => ({
    ...b,
    status: editorBreaks[String(i)]?.status ?? b.status,
    timestamp: editorBreaks[String(i)]?.timestamp ?? b.t,
  }));

  return (
    <div className="w-full" style={{ height: 140 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
          <XAxis
            dataKey="t"
            tickFormatter={formatTime}
            tick={{ fill: "#475569", fontSize: 10 }}
            axisLine={{ stroke: "#334155" }}
            tickLine={false}
          />
          <YAxis yAxisId="rms" domain={[0, 1]} hide />
          <YAxis yAxisId="semantic" domain={[0, 1]} tick={{ fill: "#475569", fontSize: 10 }} width={28} />

          {/* Grey RMS fill */}
          <Area
            yAxisId="rms"
            dataKey="rms"
            fill="#475569"
            stroke="none"
            opacity={0.35}
            isAnimationActive={false}
          />

          {/* Teal semantic score */}
          <Line
            yAxisId="semantic"
            dataKey="semantic"
            stroke="#14b8a6"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />

          {/* SegmentIQ breaks — teal */}
          {activeBreaks
            .filter((b) => b.status !== "rejected")
            .map((b, i) => (
              <ReferenceLine
                key={`sq-${i}`}
                x={b.timestamp}
                yAxisId="semantic"
                stroke={b.status === "accepted" ? "#10b981" : "#14b8a6"}
                strokeWidth={2}
                onClick={() => onBreakClick(b.timestamp)}
                style={{ cursor: "pointer" }}
              />
            ))}

          {/* Fixed-interval baseline — grey dashed */}
          {signals.fixed_interval_breaks.map((b, i) => (
            <ReferenceLine
              key={`fi-${i}`}
              x={b.t}
              yAxisId="semantic"
              stroke="#64748b"
              strokeDasharray="4 4"
              strokeWidth={1}
            />
          ))}

          <Tooltip content={<CustomTooltip signals={signals} />} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
