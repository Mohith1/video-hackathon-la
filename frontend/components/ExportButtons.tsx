"use client";
import { getExportUrl } from "@/lib/api";

interface Props {
  videoId: string;
}

export default function ExportButtons({ videoId }: Props) {
  return (
    <div className="flex gap-2">
      {(["json", "xml", "edl"] as const).map((fmt) => (
        <a
          key={fmt}
          href={getExportUrl(videoId, fmt)}
          download
          className="btn-ghost uppercase tracking-wide"
        >
          {fmt}
        </a>
      ))}
    </div>
  );
}
