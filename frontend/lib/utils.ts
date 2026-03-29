export function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds - Math.floor(seconds)) * 10);
  if (h > 0) return `${h}:${pad(m)}:${pad(s)}.${ms}`;
  return `${pad(m)}:${pad(s)}.${ms}`;
}

function pad(n: number): string {
  return n.toString().padStart(2, "0");
}

export function cn(...classes: (string | undefined | false | null)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}
