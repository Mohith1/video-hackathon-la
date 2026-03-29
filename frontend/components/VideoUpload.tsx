"use client";
import { useRef, useState } from "react";
import { uploadVideo, importFromS3 } from "@/lib/api";

const MODES = [
  { value: "ad_break", label: "Ad-Break", desc: "Sports broadcast - find natural pauses" },
  { value: "news", label: "News", desc: "Topic transitions & story boundaries" },
  { value: "structural", label: "Structural", desc: "Act structure, cold open, credits" },
];

const S3_PRESETS = [
  {
    label: "Jimmy.mp4",
    desc: "13.8 min · Structural demo",
    uri: "s3://twelvelabs-bedrock-workshop-workshopbucket-pta7wtkszqkf/test-videos/Jimmy.mp4",
    mode: "structural",
  },
  {
    label: "youtube-shorts.mp4",
    desc: "3.4 min · Quick test",
    uri: "s3://twelvelabs-bedrock-workshop-workshopbucket-pta7wtkszqkf/test-videos/youtube-shorts.mp4",
    mode: "structural",
  },
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
  const [tab, setTab] = useState<"upload" | "s3">("upload");
  const [s3Uri, setS3Uri] = useState("");
  const [s3Mode, setS3Mode] = useState("structural");
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
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) handleFile(droppedFile);
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

  const handleS3Import = async (uri?: string, selectedMode?: string) => {
    const finalUri = uri || s3Uri;
    const finalMode = selectedMode || s3Mode;
    if (!finalUri.startsWith("s3://")) {
      setError("URI must start with s3://");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const { video_id } = await importFromS3(finalUri, finalMode);
      onComplete(video_id);
    } catch (e: any) {
      setError(e.message || "Import failed");
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex overflow-hidden rounded-xl border border-slate-200 bg-slate-100 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
        <button
          onClick={() => setTab("upload")}
          className={`flex-1 py-2 text-sm font-medium transition-all ${
            tab === "upload"
              ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white"
              : "bg-transparent text-slate-600 hover:bg-white/70 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          }`}
        >
          Upload Video
        </button>
        <button
          onClick={() => setTab("s3")}
          className={`flex-1 py-2 text-sm font-medium transition-all ${
            tab === "s3"
              ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white"
              : "bg-transparent text-slate-600 hover:bg-white/70 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          }`}
        >
          Use S3 Video
        </button>
      </div>

      {tab === "upload" && (
        <>
          <div className="grid grid-cols-3 gap-2">
            {MODES.map((entry) => (
              <button
                key={entry.value}
                onClick={() => setMode(entry.value)}
                className={`rounded-lg border p-3 text-left transition-all ${
                  mode === entry.value
                    ? "border-teal-400 bg-teal-50 text-teal-700 shadow-sm dark:border-teal-500 dark:bg-teal-500/10 dark:text-teal-400"
                    : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-slate-600"
                }`}
              >
                <div className="text-sm font-medium">{entry.label}</div>
                <div className="mt-0.5 text-xs opacity-70">{entry.desc}</div>
              </button>
            ))}
          </div>

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition-all ${
              dragging
                ? "border-teal-400 bg-teal-50 dark:border-teal-500 dark:bg-teal-500/5"
                : file
                  ? "border-emerald-400 bg-emerald-50 dark:border-emerald-600 dark:bg-emerald-900/10"
                  : "border-slate-300 bg-slate-50 hover:border-slate-400 dark:border-slate-700 dark:bg-slate-800/50 dark:hover:border-slate-600"
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
                <div className="text-sm font-medium text-emerald-600 dark:text-emerald-400">{file.name}</div>
                <div className="text-xs text-slate-500">
                  {(file.size / 1024 / 1024).toFixed(1)} MB · Ready to process
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="text-sm text-slate-700 dark:text-slate-400">Drop video here or click to browse</div>
                <div className="text-xs text-slate-500 dark:text-slate-600">MP4 · MOV · MKV · 45-90 min recommended</div>
              </div>
            )}
          </div>

          {error && <div className="text-center text-sm text-red-600 dark:text-red-400">{error}</div>}

          <button
            onClick={handleSubmit}
            disabled={!file || uploading}
            className={`w-full rounded-lg py-3 font-medium transition-all ${
              file && !uploading
                ? "bg-teal-500 text-white hover:bg-teal-600"
                : "cursor-not-allowed bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-500"
            }`}
          >
            {uploading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></span>
                Processing...
              </span>
            ) : (
              `Analyze with ${MODES.find((entry) => entry.value === mode)?.label} Mode`
            )}
          </button>
        </>
      )}

      {tab === "s3" && (
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="px-1 text-xs text-slate-500">Workshop videos in S3</div>
            {S3_PRESETS.map((preset) => (
              <div
                key={preset.uri}
                className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-800"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-300">{preset.label}</div>
                  <div className="text-xs text-slate-500">{preset.desc}</div>
                </div>
                {MODES.map((entry) => (
                  <button
                    key={entry.value}
                    disabled={uploading}
                    onClick={() => handleS3Import(preset.uri, entry.value)}
                    className={`rounded px-3 py-1.5 text-xs font-medium transition-all ${
                      uploading
                        ? "cursor-not-allowed bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-500"
                        : "bg-slate-100 text-slate-700 hover:bg-teal-600 hover:text-white dark:bg-slate-700 dark:text-slate-300"
                    }`}
                  >
                    {entry.label}
                  </button>
                ))}
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-600">
            <div className="h-px flex-1 bg-slate-200 dark:bg-slate-800"></div>
            <span>or enter custom URI</span>
            <div className="h-px flex-1 bg-slate-200 dark:bg-slate-800"></div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {MODES.map((entry) => (
              <button
                key={entry.value}
                onClick={() => setS3Mode(entry.value)}
                className={`rounded-lg border p-2 text-center text-xs transition-all ${
                  s3Mode === entry.value
                    ? "border-teal-400 bg-teal-50 text-teal-700 dark:border-teal-500 dark:bg-teal-500/10 dark:text-teal-400"
                    : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:border-slate-600"
                }`}
              >
                {entry.label}
              </button>
            ))}
          </div>

          <input
            type="text"
            placeholder="s3://bucket/path/to/video.mp4"
            value={s3Uri}
            onChange={(e) => setS3Uri(e.target.value)}
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-mono text-slate-800 placeholder-slate-400 focus:border-teal-500 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:placeholder-slate-600"
          />

          {error && <div className="text-center text-sm text-red-600 dark:text-red-400">{error}</div>}

          <button
            onClick={() => handleS3Import()}
            disabled={!s3Uri || uploading}
            className={`w-full rounded-lg py-3 text-sm font-medium transition-all ${
              s3Uri && !uploading
                ? "bg-teal-500 text-white hover:bg-teal-600"
                : "cursor-not-allowed bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-500"
            }`}
          >
            {uploading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></span>
                Processing...
              </span>
            ) : (
              `Analyze with ${MODES.find((entry) => entry.value === s3Mode)?.label} Mode`
            )}
          </button>
        </div>
      )}
    </div>
  );
}
