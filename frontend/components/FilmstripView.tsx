"use client";
import useSWR from "swr";
import { getFilmstrip } from "@/lib/api";

const fetcher = ([videoId, breakId]: [string, string]) =>
  getFilmstrip(videoId, breakId);

interface Props {
  videoId: string;
  breakId: string;
}

export default function FilmstripView({ videoId, breakId }: Props) {
  const { data, isLoading } = useSWR([videoId, breakId], fetcher, {
    revalidateOnFocus: false,
  });

  if (isLoading) {
    return (
      <div className="flex gap-2 items-center my-2">
        <div className="w-[120px] h-[68px] bg-slate-700 animate-pulse rounded border border-slate-600" />
        <span className="text-slate-600 text-xs">→</span>
        <div className="w-[120px] h-[68px] bg-slate-700 animate-pulse rounded border border-slate-600" />
      </div>
    );
  }

  if (!data?.before_frame_url) {
    return (
      <div className="flex gap-2 items-center my-2 text-slate-600 text-xs">
        <div className="w-[120px] h-[68px] bg-slate-800 rounded border border-slate-700 flex items-center justify-center">
          before
        </div>
        <span>→</span>
        <div className="w-[120px] h-[68px] bg-slate-800 rounded border border-slate-700 flex items-center justify-center">
          after
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-2 items-center my-2">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={data.before_frame_url}
        alt="Before cut"
        width={120}
        height={68}
        className="rounded border border-slate-600 object-cover"
      />
      <span className="text-slate-400 text-xs">→</span>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={data.after_frame_url}
        alt="After cut"
        width={120}
        height={68}
        className="rounded border border-slate-600 object-cover"
      />
    </div>
  );
}
