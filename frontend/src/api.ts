// Cliente da API Python (snake_case, sem wrapper). Mesma origem → URLs relativos.

export interface Court {
  id: string;
  name: string;
  camera_ip: string;
  nvr_user: string;
  nvr_password: string;
  rtsp_path: string | null;
  youtube_stream_key: string | null;
  youtube_broadcast_id: string | null;
  youtube_watch_url: string | null;
  logo_path: string | null;
  logo_position: string;
  logo_size_percent: number;
  logo_opacity: number;
  resolution: string;
  bitrate_kbps: number;
  fps: number;
  crop_region: string | null;
  overlay_text: string | null;
  show_clock: boolean;
  overlay_text_position: string;
  overlay_font_size: number;
  overlay_font_color: string;
  overlay_font_family: string;
  audio_volume: number;
  audio_normalize: boolean;
  audio_denoise: boolean;
  audio_denoise_strength: number;
}

export interface StreamStatus {
  court_id: string;
  is_running: boolean;
  pid: number;
  started_at: string | null;
  restart_count: number;
  last_error: string | null;
}

async function j<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.status === 204 ? (null as T) : res.json();
}

export const api = {
  listCourts: () => j<Court[]>("/api/courts"),
  getCourt: (id: string) => j<Court>(`/api/courts/${id}`),
  createCourt: (name: string) =>
    j<Court>("/api/courts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }),
  updateCourt: (id: string, patch: Partial<Court>) =>
    j<Court>(`/api/courts/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }),
  start: (id: string) => j<StreamStatus>(`/api/courts/${id}/start`, { method: "POST" }),
  stop: (id: string) => j<any>(`/api/courts/${id}/stop`, { method: "POST" }),
  status: (id: string) => j<StreamStatus>(`/api/courts/${id}/status`),
  snapshotUrl: (id: string) => `/api/courts/${id}/snapshot?t=${Date.now()}`,
  uploadLogo: async (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return j<{ logo_path: string; logo_url: string }>(`/api/courts/${id}/logo`, { method: "POST", body: fd });
  },
};
