type Draft = { ownerUid?: string; fileNo?: string; sourceFileName?: string; link?: string; time: number };
const KEY = "asr-upload-draft";
export function readUploadDraft(): Draft | null {
  try { const data = JSON.parse(sessionStorage.getItem(KEY) || "null") as Draft | null;
    return data && Date.now() - data.time < 3600_000 ? data : null;
  } catch { return null; }
}
export function saveUploadDraft(patch: Partial<Draft>) {
  sessionStorage.setItem(KEY, JSON.stringify({ ...readUploadDraft(), ...patch, time: Date.now() }));
}
export function clearUploadDraft() { sessionStorage.removeItem(KEY); }
