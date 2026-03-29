import { create } from "zustand";

export type BreakStatus = "pending" | "accepted" | "rejected";

export interface BreakState {
  timestamp: number;
  score: number;
  status: BreakStatus;
  visual: number;
  silence: number;
  semantic: number;
  description?: string;
}

interface EditorStore {
  breaks: Record<string, BreakState>;
  videoId: string | null;
  mode: string;
  k: number;
  minGapSec: number;
  duration: number;
  setVideoData: (videoId: string, breaks: BreakState[], mode: string, duration: number) => void;
  setMode: (mode: string) => void;
  setK: (k: number) => void;
  setMinGapSec: (v: number) => void;
  nudgeBreak: (breakId: string, deltaSec: number) => number;
  acceptBreak: (breakId: string) => void;
  rejectBreak: (breakId: string) => void;
  restoreBreak: (breakId: string) => void;
  updateBreaks: (breaks: BreakState[]) => void;
  getExportBreaks: () => BreakState[];
}

export const useEditorStore = create<EditorStore>((set, get) => ({
  breaks: {},
  videoId: null,
  mode: "ad_break",
  k: 6,
  minGapSec: 480,
  duration: 3600,

  setVideoData: (videoId, breaks, mode, duration) => {
    const breakMap: Record<string, BreakState> = {};
    breaks.forEach((b, i) => { breakMap[String(i)] = b; });
    set({ videoId, breaks: breakMap, mode, duration });
  },

  setMode: (mode) => set({ mode }),
  setK: (k) => set({ k }),
  setMinGapSec: (v) => set({ minGapSec: v }),

  nudgeBreak: (breakId, deltaSec) => {
    const current = get().breaks[breakId];
    if (!current) return 0;
    const newTs = Math.max(0, Math.min(get().duration, current.timestamp + deltaSec));
    set((s) => ({
      breaks: { ...s.breaks, [breakId]: { ...s.breaks[breakId], timestamp: newTs } },
    }));
    return newTs;
  },

  acceptBreak: (breakId) =>
    set((s) => ({
      breaks: { ...s.breaks, [breakId]: { ...s.breaks[breakId], status: "accepted" } },
    })),

  rejectBreak: (breakId) =>
    set((s) => ({
      breaks: { ...s.breaks, [breakId]: { ...s.breaks[breakId], status: "rejected" } },
    })),

  restoreBreak: (breakId) =>
    set((s) => ({
      breaks: { ...s.breaks, [breakId]: { ...s.breaks[breakId], status: "pending" } },
    })),

  updateBreaks: (breaks) => {
    const breakMap: Record<string, BreakState> = {};
    breaks.forEach((b, i) => { breakMap[String(i)] = b; });
    set({ breaks: breakMap });
  },

  getExportBreaks: () =>
    Object.values(get().breaks).filter((b) => b.status !== "rejected"),
}));
