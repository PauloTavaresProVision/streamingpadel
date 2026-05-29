import React, { useEffect, useRef, useState } from "react";
import { Radio, Play, Square, Upload, Save, ExternalLink, Clock, Type } from "lucide-react";
import { Button } from "./ui";
import { api, Court, StreamStatus } from "./api";
import { LogoPositioner } from "./components/LogoPositioner";
import { CropSelector } from "./components/CropSelector";

const RES = ["720p", "1080p"];
const TEXT_POS = ["TopLeft", "TopCenter", "TopRight", "BottomLeft", "BottomCenter", "BottomRight"];
const FONTS = ["Sans", "Serif", "Monospace"];

export default function App() {
  const [courts, setCourts] = useState<Court[]>([]);
  const [court, setCourt] = useState<Court | null>(null);
  const [status, setStatus] = useState<StreamStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [snapUrl, setSnapUrl] = useState<string | null>(null);
  const [snapLoading, setSnapLoading] = useState(false);
  const [snapErr, setSnapErr] = useState<string | null>(null);
  const [toast, setToast] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(""), 2600); };

  const loadCourts = async () => {
    const cs = await api.listCourts();
    setCourts(cs);
    if (cs.length && (!court || !cs.find((c) => c.id === court.id))) select(cs[0]);
  };
  const select = (c: Court) => {
    setCourt(c);
    refreshStatus(c.id);
    setSnapUrl(null); setSnapErr(null);
  };
  const patch = (k: keyof Court, v: any) => setCourt((c) => (c ? { ...c, [k]: v } : c));

  const save = async () => {
    if (!court) return;
    setBusy(true);
    try {
      const updated = await api.updateCourt(court.id, court);
      setCourt(updated);
      await loadCourts();
      showToast("Configuração guardada");
    } catch (e: any) { showToast("Erro: " + e.message); }
    finally { setBusy(false); }
  };

  const start = async () => {
    if (!court) return;
    setBusy(true);
    try { await api.updateCourt(court.id, court); await api.start(court.id); showToast("Transmissão iniciada"); refreshStatus(court.id); }
    catch (e: any) { showToast("Erro a iniciar: " + e.message); }
    finally { setBusy(false); }
  };
  const stop = async () => {
    if (!court) return;
    setBusy(true);
    try { await api.stop(court.id); showToast("Transmissão parada"); refreshStatus(court.id); }
    catch (e: any) { showToast("Erro: " + e.message); }
    finally { setBusy(false); }
  };

  const refreshStatus = async (id: string) => {
    try { setStatus(await api.status(id)); } catch {}
  };
  const refreshSnap = async () => {
    if (!court) return;
    setSnapLoading(true); setSnapErr(null);
    const url = api.snapshotUrl(court.id);
    const img = new Image();
    img.onload = () => { setSnapUrl(url); setSnapLoading(false); };
    img.onerror = () => { setSnapErr("Câmara inacessível"); setSnapLoading(false); };
    img.src = url;
  };
  const onLogo = async (f: File) => {
    if (!court) return;
    try { const r = await api.uploadLogo(court.id, f); patch("logo_path", r.logo_path); showToast("Logo carregado"); }
    catch (e: any) { showToast("Erro no logo: " + e.message); }
  };

  useEffect(() => { loadCourts(); }, []);
  useEffect(() => {
    if (!court) return;
    const t = setInterval(() => refreshStatus(court.id), 5000);
    return () => clearInterval(t);
  }, [court?.id]);

  const running = status?.is_running;
  const logoUrl = court?.logo_path ? `/data/${court.logo_path}?t=${court.id}` : null;

  return (
    <div className="min-h-full">
      {/* App bar */}
      <div className="sticky top-0 z-20 bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2 font-bold text-slate-800">
          <span className="w-2.5 h-2.5 rounded-full bg-red-600" style={{ boxShadow: "0 0 0 4px rgba(220,38,38,.18)" }} />
          Padel Streamer <span className="text-slate-400 font-normal text-sm">— YouTube · Jetson NVENC</span>
        </div>
        <a href="/test" className="text-xs text-slate-400 hover:text-slate-600">Página de teste</a>
      </div>

      <div className="max-w-6xl mx-auto p-6">
        {/* Court tabs */}
        <div className="flex gap-2 flex-wrap mb-5">
          {courts.map((c) => (
            <button key={c.id} onClick={() => select(c)}
              className={`px-4 py-2 rounded-full text-sm font-semibold border transition ${court?.id === c.id ? "bg-blue-600 text-white border-blue-600" : "bg-white text-slate-500 border-slate-300 hover:border-blue-500"}`}>
              {c.name}
            </button>
          ))}
        </div>

        {court && (
          <div className="grid lg:grid-cols-2 gap-5 items-start">
            {/* LEFT: preview + controlo */}
            <div className="space-y-5 lg:sticky lg:top-20">
              <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-xs uppercase tracking-wide font-bold text-slate-500">Transmissão</h2>
                  <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold ${running ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-500"}`}>
                    <span className={`w-2 h-2 rounded-full ${running ? "bg-red-600 animate-pulse" : "bg-slate-400"}`} />
                    {running ? `LIVE · pid ${status?.pid}` : "OFFLINE"}
                  </span>
                </div>

                {/* Preview grande com logo + crop */}
                <LogoPositioner
                  snapshotUrl={snapUrl}
                  isLoadingSnapshot={snapLoading}
                  snapshotError={snapErr}
                  logoUrl={logoUrl}
                  logoSizePercent={court.logo_size_percent}
                  logoOpacity={court.logo_opacity}
                  position={court.logo_position}
                  cropRegion={court.crop_region ?? ""}
                  onPositionChange={(p) => patch("logo_position", p)}
                  onSizeChange={(s) => patch("logo_size_percent", s)}
                  onRefresh={refreshSnap}
                />

                {status?.last_error && (
                  <pre className="mt-3 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg p-2 whitespace-pre-wrap max-h-32 overflow-auto">{status.last_error.slice(-500)}</pre>
                )}

                <div className="flex gap-2 mt-4">
                  {running ? (
                    <Button variant="stop" className="flex-1" onClick={stop} disabled={busy}><Square className="h-4 w-4" /> Parar</Button>
                  ) : (
                    <Button variant="danger" className="flex-1" onClick={start} disabled={busy || !court.youtube_stream_key}><Play className="h-4 w-4" /> Iniciar transmissão</Button>
                  )}
                </div>
                {court.youtube_watch_url && (
                  <a href={court.youtube_watch_url} target="_blank" className="inline-flex items-center gap-1 text-sm text-blue-600 mt-3"><ExternalLink className="h-4 w-4" /> Ver no YouTube</a>
                )}
              </div>

              {/* Crop */}
              <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
                <CropSelector
                  snapshotUrl={snapUrl}
                  isLoadingSnapshot={snapLoading}
                  snapshotError={snapErr}
                  cropRegion={court.crop_region ?? ""}
                  onCropChange={(c) => patch("crop_region", c || null)}
                />
              </div>
            </div>

            {/* RIGHT: config */}
            <div className="space-y-5">
              <Card title="Câmara">
                <Field label="Nome do campo"><input className="inp" value={court.name} onChange={(e) => patch("name", e.target.value)} /></Field>
                <div className="flex gap-3">
                  <Field label="IP da câmara"><input className="inp" value={court.camera_ip} onChange={(e) => patch("camera_ip", e.target.value)} /></Field>
                  <Field label="Caminho RTSP"><input className="inp" value={court.rtsp_path ?? ""} onChange={(e) => patch("rtsp_path", e.target.value)} /></Field>
                </div>
                <div className="flex gap-3">
                  <Field label="Utilizador"><input className="inp" value={court.nvr_user} onChange={(e) => patch("nvr_user", e.target.value)} /></Field>
                  <Field label="Password"><input type="password" className="inp" value={court.nvr_password} onChange={(e) => patch("nvr_password", e.target.value)} /></Field>
                </div>
              </Card>

              <Card title="YouTube & Vídeo">
                <Field label="Stream key do YouTube"><input className="inp" placeholder="xxxx-xxxx-xxxx-xxxx-xxxx" value={court.youtube_stream_key ?? ""} onChange={(e) => patch("youtube_stream_key", e.target.value)} /></Field>
                <div className="flex gap-3">
                  <Field label="Resolução"><select className="inp" value={court.resolution} onChange={(e) => patch("resolution", e.target.value)}>{RES.map((r) => <option key={r}>{r}</option>)}</select></Field>
                  <Field label="Bitrate (kbps)"><input type="number" className="inp" value={court.bitrate_kbps} onChange={(e) => patch("bitrate_kbps", +e.target.value)} /></Field>
                  <Field label="FPS"><input type="number" className="inp" value={court.fps} onChange={(e) => patch("fps", +e.target.value)} /></Field>
                </div>
              </Card>

              <Card title="Logo">
                <div className="flex items-center gap-2">
                  <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && onLogo(e.target.files[0])} />
                  <Button variant="outline" onClick={() => fileRef.current?.click()}><Upload className="h-4 w-4" /> Carregar logo</Button>
                  {court.logo_path && <span className="text-xs text-slate-500">{court.logo_path}</span>}
                </div>
                <Field label={`Opacidade: ${court.logo_opacity}%`}>
                  <input type="range" min={10} max={100} step={5} className="w-full" value={court.logo_opacity} onChange={(e) => patch("logo_opacity", +e.target.value)} />
                </Field>
                <p className="text-xs text-slate-500">Arrasta o logo no preview à esquerda para posicionar; usa a alça para redimensionar.</p>
              </Card>

              <Card title="Texto e hora">
                <Field label="Texto fixo (opcional)"><input className="inp" placeholder="Ex: GameVision — Campo 1" value={court.overlay_text ?? ""} onChange={(e) => patch("overlay_text", e.target.value)} /></Field>
                <label className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl px-3 py-3 mt-3 cursor-pointer">
                  <span className="text-sm font-semibold text-slate-700 flex items-center gap-2"><Clock className="h-4 w-4" /> Mostrar hora actual</span>
                  <input type="checkbox" checked={court.show_clock} onChange={(e) => patch("show_clock", e.target.checked)} />
                </label>
                <div className="flex gap-3 flex-wrap">
                  <Field label="Posição"><select className="inp" value={court.overlay_text_position} onChange={(e) => patch("overlay_text_position", e.target.value)}>{TEXT_POS.map((p) => <option key={p}>{p}</option>)}</select></Field>
                  <Field label="Tamanho"><input type="number" className="inp" value={court.overlay_font_size} onChange={(e) => patch("overlay_font_size", +e.target.value)} /></Field>
                  <Field label="Fonte"><select className="inp" value={court.overlay_font_family} onChange={(e) => patch("overlay_font_family", e.target.value)}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select></Field>
                  <Field label="Cor"><input type="color" className="inp h-10" value={(court.overlay_font_color || "#ffffff").startsWith("#") ? court.overlay_font_color : "#ffffff"} onChange={(e) => patch("overlay_font_color", e.target.value)} /></Field>
                </div>
              </Card>

              <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
                <Button onClick={save} disabled={busy}><Save className="h-4 w-4" /> Guardar configuração</Button>
              </div>
            </div>
          </div>
        )}
      </div>

      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-5 py-3 rounded-xl shadow-lg text-sm">{toast}</div>}

      <style>{`.inp{width:100%;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px;background:#fff;outline:none}
      .inp:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.12)}`}</style>
    </div>
  );
}

const Card: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
    <h2 className="text-xs uppercase tracking-wide font-bold text-slate-500 mb-3">{title}</h2>
    <div className="space-y-1">{children}</div>
  </div>
);
const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex-1 min-w-[120px]">
    <label className="block text-xs font-semibold text-slate-500 mb-1.5 mt-3 first:mt-0">{label}</label>
    {children}
  </div>
);
