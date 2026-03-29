const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function apiHttpUrl(path: string): string {
  // Resolve all endpoints from API origin root, ignoring accidental path suffixes
  // in NEXT_PUBLIC_API_URL (e.g. ".../videos" or ".../api").
  try {
    return new URL(path, API_URL).toString();
  } catch {
    return `${API_URL.replace(/\/+$/, "")}${path}`;
  }
}

function apiWsUrl(path: string): string {
  try {
    const base = new URL(API_URL);
    base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
    base.pathname = path;
    base.search = "";
    base.hash = "";
    return base.toString();
  } catch {
    const wsBase = API_URL.replace(/^http/, "ws").replace(/\/+$/, "");
    return `${wsBase}${path}`;
  }
}

export async function uploadVideo(file: File, mode: string): Promise<{ video_id: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("mode", mode);
  const res = await fetch(apiHttpUrl("/api/videos"), { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getVideo(videoId: string): Promise<any> {
  const res = await fetch(apiHttpUrl(`/api/videos/${videoId}`));
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function importFromS3(s3Uri: string, mode: string): Promise<{ video_id: string }> {
  const res = await fetch(apiHttpUrl("/api/videos/import-s3"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ s3_uri: s3Uri, mode }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function optimizeVideo(videoId: string, mode: string, k?: number, minGapSec?: number) {
  const res = await fetch(apiHttpUrl(`/api/videos/${videoId}/optimize`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, k, min_gap_sec: minGapSec }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getFilmstrip(videoId: string, breakId: string) {
  const res = await fetch(apiHttpUrl(`/api/videos/${videoId}/breaks/${breakId}/filmstrip`));
  if (!res.ok) return null;
  return res.json();
}

export async function generateTransition(videoId: string, breakId: string) {
  const res = await fetch(apiHttpUrl(`/api/videos/${videoId}/breaks/${breakId}/generate-transition`), {
    method: "POST",
  });
  if (!res.ok) return null;
  return res.json();
}

export function getExportUrl(videoId: string, format: "json" | "xml" | "edl") {
  return apiHttpUrl(`/api/videos/${videoId}/export?format=${format}`);
}

export function createWebSocket(videoId: string): WebSocket {
  return new WebSocket(apiWsUrl(`/ws/videos/${videoId}/progress`));
}
