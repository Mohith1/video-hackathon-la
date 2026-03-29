"use client";
import { useRouter } from "next/navigation";
import VideoUpload from "@/components/VideoUpload";

export default function HomePage() {
  const router = useRouter();

  const handleUploadComplete = (videoId: string) => {
    router.push(`/videos/${videoId}`);
  };

  return (
    <div className="min-h-[calc(100vh-53px)] flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-2xl space-y-8">

        {/* Hero */}
        <div className="text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border mb-2"
            style={{ borderColor: "var(--border)", color: "var(--text-3)", backgroundColor: "var(--bg-subtle)" }}>
            <span className="w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse"></span>
            TwelveLabs Marengo + Pegasus · AWS Bedrock
          </div>
          <h1 className="text-4xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
            Intelligent Video<br />
            <span className="text-teal-500">Segmentation</span>
          </h1>
          <p className="text-sm leading-relaxed max-w-md mx-auto" style={{ color: "var(--text-2)" }}>
            Narrative AI fuses visual embeddings, audio signals, and semantic understanding
            to find natural narrative boundaries — not arbitrary intervals.
          </p>
          <div className="flex gap-5 justify-center text-xs pt-1" style={{ color: "var(--text-3)" }}>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-teal-500"></span>
              Marengo visual
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-400"></span>
              Pegasus semantic
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "var(--text-3)" }}></span>
              Audio silence
            </span>
          </div>
        </div>

        {/* Upload card */}
        <div className="card shadow-xl">
          <VideoUpload onComplete={handleUploadComplete} />
        </div>

        {/* Mode cards */}
        <div className="grid grid-cols-3 gap-3 text-center text-xs">
          {[
            { mode: "Ad-Break", desc: "Sports · 5–7 natural pauses", color: "text-teal-500" },
            { mode: "News", desc: "Story boundaries · topic labels", color: "text-blue-400" },
            { mode: "Structural", desc: "Cold open · acts · credits", color: "text-purple-400" },
          ].map((m) => (
            <div key={m.mode} className="rounded-xl border p-3 transition-colors"
              style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-subtle)" }}>
              <div className={`${m.color} font-semibold mb-1`}>{m.mode}</div>
              <div style={{ color: "var(--text-3)" }}>{m.desc}</div>
            </div>
          ))}
        </div>

      </div>
    </div>
  );
}
