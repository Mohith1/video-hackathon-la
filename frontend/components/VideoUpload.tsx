"use client";
import { useState, useRef } from "react";
import { uploadVideo, importFromS3 } from "@/lib/api";

const MODES = [
  { value: "ad_break", label: "Ad-Break", desc: "Sports broadcast — find natural pauses" },
  { value: "news", label: "News", desc: "Topic transitions & story boundaries" },
  { value: "structural", label: "Structural", desc: "Act structure, cold open, credits" },
];

interface Props {
  onComplete: (videoId: string) => void;
}

export default function VideoUpload({ onComplete }: Props) {
  const [mode, setMode] = useState("ad_break");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showS3, setShowS3] = useState(false);
  const [s3Uri, setS3Uri] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    if (!f.type.startsWith("video/") && !f.name.match(/\.(mp4|mov|mkv|avi|webm)$/i)) {
      setError("Please upload a video file (MP4, MOV, MKV, AVI, WebM)");
      return;
    }
    setFile(f);
    setError(null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  };

  const handleSubmit = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const { video_id } = await uploadVideo(file, mode);
      onComplete(video_id);
    } catch (e: any) {
      setError(e.message || "Upload failed");
      setUploading(false);
    }
  };

  const handleS3Import = async () => {
    if (!s3Uri.startsWith("s3://")) {
      setError("URI must start with s3://");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const { video_id } = await importFromS3(s3Uri, mode);
      onComplete(video_id);
    } catch (e: any) {
      setError(e.message || "Import failed");
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Mode selector */}
      <div className="grid grid-cols-3 gap-2">
        {MODES.map((m) => (
          <button
            key={m.value}
            onClick={() => setMode(m.value)}
            className={`p-3 rounded-lg border text-left transition-all ${
              mode === m.value
                ? "border-teal-500 bg-teal-500/10 text-teal-400"
                : "border-slate-700 bg-slate-800 text-slate-400 hover:border-slate-600"
            }`}
          >
            <div className="font-medium text-sm">{m.label}</div>
            <div className="text-xs mt-0.5 opacity-70">{m.desc}</div>
          </button>
        ))}
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all ${
          dragging
            ? "border-teal-500 bg-teal-500/5"
            : file
            ? "border-emerald-600 bg-emerald-900/10"
            : "border-slate-700 bg-slate-800/50 hover:border-slate-600"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/*,.mkv"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {file ? (
          <div className="space-y-1">
            <div className="text-emerald-400 text-sm font-medium">{file.name}</div>
            <div className="text-slate-500 text-xs">
              {(file.size / 1024 / 1024).toFixed(1)} MB · Ready to process
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-slate-400 text-sm">Drop video here or click to browse</div>
            <div className="text-slate-600 text-xs">MP4 · MOV · MKV · 45–90 min recommended</div>
          </div>
        )}
      </div>

      {error && <div className="text-red-400 text-sm text-center">{error}</div>}

      <button
        onClick={handleSubmit}
        disabled={!file || uploading}
        className={`w-full py-3 rounded-lg font-medium transition-all ${
          file && !uploading
            ? "bg-teal-500 hover:bg-teal-600 text-white"
            : "bg-slate-700 text-slate-500 cursor-not-allowed"
        }`}
      >
        {uploading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
            Processing...
          </span>
        ) : (
          `Analyze with ${MODES.find((m2) => m2.value === mode)?.label} Mode`
        )}
      </button>

      <div className="flex items-center gap-2 text-xs text-slate-600">
        <div className="flex-1 h-px bg-slate-800"></div>
        <button onClick={() => setShowS3(!showS3)} className="hover:text-slate-400 transition-colors">
          {showS3 ? "hide" : "or use existing S3 video"}
        </button>
        <div className="flex-1 h-px bg-slate-800"></div>
      </div>

      {showS3 && (
        <div className="space-y-2">
          <input
            type="text"
            placeholder="s3://bucket/path/to/video.mp4"
            value={s3Uri}
            onChange={(e) => setS3Uri(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-300 placeholder-slate-600 focus:outline-none focus:border-teal-500"
          />
          <button
            onClick={handleS3Import}
            disabled={!s3Uri || uploading}
            className={`w-full py-2 rounded-lg text-sm font-medium transition-all ${
              s3Uri && !uploading
                ? "bg-blue-600 hover:bg-blue-700 text-white"
                : "bg-slate-700 text-slate-500 cursor-not-allowed"
            }`}
          >
            Process S3 Video
          </button>
        </div>
      )}
    </div>
  );
}
