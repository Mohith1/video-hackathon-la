"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import VideoUpload from "@/components/VideoUpload";

export default function HomePage() {
  const router = useRouter();
  const [isUploading, setIsUploading] = useState(false);

  const handleUploadComplete = (videoId: string) => {
    router.push(`/videos/${videoId}`);
  };

  return (
    <div className="min-h-[calc(100vh-53px)] flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-2xl space-y-8">
        <div className="text-center space-y-3">
          <h1 className="text-3xl font-bold text-white tracking-tight">
            Intelligent Video Segmentation
          </h1>
          <p className="text-slate-400 text-sm leading-relaxed max-w-lg mx-auto">
            Upload a video (45–90 min). SegmentIQ fuses visual, audio, and semantic signals
            to find natural narrative boundaries — not arbitrary intervals.
          </p>
          <div className="flex gap-4 justify-center text-xs text-slate-500 pt-1">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-teal-500"></span>
              Marengo visual embeddings
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-blue-400"></span>
              Pegasus scene reasoning
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-slate-400"></span>
              Audio silence detection
            </span>
          </div>
        </div>

        <VideoUpload onComplete={handleUploadComplete} />

        <div className="grid grid-cols-3 gap-4 text-center text-xs">
          {[
            { mode: "Ad-Break", desc: "Sports broadcast · 5-7 natural pauses", color: "teal" },
            { mode: "News", desc: "Story boundaries · topic transitions", color: "blue" },
            { mode: "Structural", desc: "Episodic · cold open / acts / credits", color: "purple" },
          ].map((m) => (
            <div key={m.mode} className="card">
              <div className={`text-${m.color}-400 font-medium mb-1`}>{m.mode}</div>
              <div className="text-slate-500">{m.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
