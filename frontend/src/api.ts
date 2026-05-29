// Cliente da API Python (snake_case). Auth por bearer token em localStorage.

export interface Court {
  id: string; name: string;
  camera_ip: string; nvr_user: string; nvr_password: string; rtsp_path: string | null;
  youtube_stream_key: string | null; youtube_broadcast_id: string | null; youtube_watch_url: string | null;
  logo_path: string | null; logo_position: string; logo_size_percent: number; logo_opacity: number;
  resolution: string; bitrate_kbps: number; fps: number; crop_region: string | null;
  overlay_text: string | null; show_clock: boolean; overlay_text_position: string;
  overlay_font_size: number; overlay_font_color: string; overlay_font_family: string;
  overlay_font_bold: boolean; overlay_font_italic: boolean; overlay_bg: boolean;
  overlay_opacity: number; show_logo: boolean; show_text: boolean; show_timer: boolean;
  audio_volume: number; audio_normalize: boolean; audio_denoise: boolean; audio_denoise_strength: number;
}
export interface StreamStatus {
  court_id: string; is_running: boolean; pid: number; started_at: string | null;
  restart_count: number; last_error: string | null;
}
export interface YouTubeStatus {
  is_server_configured: boolean; is_connected: boolean;
  channel_id: string | null; channel_title: string | null; connected_at: string | null;
}

const TOKEN_KEY = "ps_token";
export const auth = {
  get: () => localStorage.getItem(TOKEN_KEY) || "",
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
  isAuthed: () => !!localStorage.getItem(TOKEN_KEY),
};

async function j<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as any) };
  const tok = auth.get();
  if (tok) headers["Authorization"] = `Bearer ${tok}`;
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) { auth.clear(); window.location.reload(); throw new Error("Sessão expirada"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.status === 204 ? (null as T) : res.json();
}

export const api = {
  login: async (password: string) => {
    const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
    if (!r.ok) throw new Error("Password incorrecta");
    const { token } = await r.json();
    auth.set(token);
  },
  logout: () => auth.clear(),

  listCourts: () => j<Court[]>("/api/courts"),
  getCourt: (id: string) => j<Court>(`/api/courts/${id}`),
  createCourt: (name: string) => j<Court>("/api/courts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }),
  updateCourt: (id: string, patch: Partial<Court>) => j<Court>(`/api/courts/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }),
  deleteCourt: (id: string) => j<void>(`/api/courts/${id}`, { method: "DELETE" }),
  start: (id: string) => j<StreamStatus>(`/api/courts/${id}/start`, { method: "POST" }),
  stop: (id: string) => j<any>(`/api/courts/${id}/stop`, { method: "POST" }),
  status: (id: string) => j<StreamStatus>(`/api/courts/${id}/status`),
  snapshotUrl: (id: string) => `/api/courts/${id}/snapshot?t=${Date.now()}`,
  uploadLogo: async (id: string, file: File) => {
    const fd = new FormData(); fd.append("file", file);
    return j<{ logo_path: string; logo_url: string }>(`/api/courts/${id}/logo`, { method: "POST", body: fd });
  },

  ytStatus: () => j<YouTubeStatus>("/api/youtube/status"),
  ytAuthUrl: () => j<{ auth_url: string }>("/api/youtube/auth-url"),
  ytDisconnect: () => j<{ ok: boolean }>("/api/youtube/disconnect", { method: "POST" }),
  createBroadcast: (id: string, body: { title: string; description?: string; privacy: string }) =>
    j<{ broadcast_id: string; stream_key: string; watch_url: string; studio_url: string }>(`/api/courts/${id}/create-broadcast`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
};
