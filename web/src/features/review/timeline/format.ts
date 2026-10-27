/** Timecode formatting: `mm:ss.s` with tabular numerals (03_UI_Spec.md §3). */
export function formatTimecode(seconds: number): string {
  const clamped = Number.isFinite(seconds) ? Math.max(seconds, 0) : 0;
  const tenths = Math.round(clamped * 10);
  const minutes = Math.floor(tenths / 600);
  const remaining = tenths % 600;
  const secs = Math.floor(remaining / 10);
  const fraction = remaining % 10;
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${fraction}`;
}
