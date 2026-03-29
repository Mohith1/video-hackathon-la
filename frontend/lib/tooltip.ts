import { formatTime } from "./utils";

export function getFixedIntervalTooltip(
  timestamp: number,
  rmsValues: number[],
  asrWordTimestamps: number[],
  asrParagraphBreaks: number[]
): string {
  const rms = rmsValues[Math.round(timestamp)] ?? 0;
  const isHighEnergy = rms > 0.60;

  const nearWord = asrWordTimestamps.some((t) => Math.abs(t - timestamp) < 2.0);
  const nearParagraph = asrParagraphBreaks.some((t) => Math.abs(t - timestamp) < 2.0);
  const isMidSentence = nearWord && !nearParagraph;

  if (isMidSentence && isHighEnergy)
    return `⚠ Cuts mid-sentence during high audio energy (${rms.toFixed(2)})`;
  if (isMidSentence)
    return `⚠ Cuts mid-sentence — no topic boundary here`;
  if (isHighEnergy)
    return `⚠ Cuts during high audio energy (${rms.toFixed(2)}) — viewer engaged`;
  return `Fixed interval — no semantic signal at ${formatTime(timestamp)}`;
}
