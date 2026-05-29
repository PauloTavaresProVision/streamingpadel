import React, { useEffect, useRef, useState } from "react";
import { Play, Square, Upload, Save, ExternalLink, Clock, Sparkles, ArrowLeft, Radio, Loader2 } from "lucide-react";
import { api, Court, StreamStatus } from "../api";
import { Button } from "../ui";
import { LogoPositioner } from "../components/LogoPositioner";
import { CropSelector } from "../components/CropSelector";

const RES = ["720p", "1080p"];
const TEXT_POS = ["TopLeft", "TopCenter", "TopRight", "BottomLeft", "BottomCenter", "BottomRight"];
const FONTS = ["Sans", "Serif", "Monospace"];

export default function Transmissoes() {
  const [courts, setCourts] = useState<Court[]>([]);
  const [statuses, setStatuses] = useState<Record<string, StreamStatus>>({});
  const [editing, setEditing] = useState<Court | null>(null);
  const [toast, setToast] = useState("");
  const t = (m: string) => { setToast(m); setTimeout(() => setToast(""), 2600); };

  const loadAll = async () => {
    const cs = await api.listCourts();
    setCourts(cs);
    const map: Record<string, StreamStatus> = {};
    await Promise.all(cs.map(async (c) => { try { map[c.id] = await api.status(c.id); } catch {} }));
    setStatuses(map);
  };
  useEffect(() => { loadAll(); const i = setInterval(loadAll, 7000); return () => clearInterval(i); }, []);

  if (editing) return <Editor court={editing} onBack={() => { setEditing(null); loadAll(); }} toast={t} toastMsg={toast} />;

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-800 mb-1">Transmissões</h1>
      <p className="text-slate-500 text-sm mb-6">Escolhe um campo para configurar e transmitir.</p>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {courts.map((c) => {
          const s = statuses[c.id];
          const live = s?.is_running;
          return (
            <button key={c.id} onClick={() => setEditing(c)}
              className="text-left bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden hover:shadow-md hover:border-blue-300 transition">
              <div className="relative aspect-video bg-slate-900">
                <img src={api.snapshotUrl(c.id)} alt="" className="w-full h-full object-cover"
                  onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
                <span className={`absolute top-2 left-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold ${live ? "bg-red-600 text-white" : "bg-black/60 text-white"}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${live ? "bg-white animate-pulse" : "bg-slate-400"}`} />
                  {live ? "LIVE" : "OFFLINE"}
                </span>
              </div>
              <div className="p-4">
                <div className="font-semibold text-slate-800">{c.name}</div>
                <div className="text-xs text-slate-400">{c.camera_ip}</div>
              </div>
            </button>
          );
        })}
      </div>
      {toast && <Toast msg={toast} />}
    </div>
  );
}

function Editor({ court: initial, onBack, toast, toastMsg }: { court: Court; onBack: () => void; toast: (m: string) => void; toastMsg: string }) {
  const [court, setCourt] = useState<Court>(initial);
  const [status, setStatus] = useState<StreamStatus | null>(null);
  const [snapUrl, setSnapUrl] = useState<string | null>(null);
  const [snapLoading, setSnapLoading] = useState(false);
  const [snapErr, setSnapErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const patch = (k: keyof Court, v: any) => setCourt((c) => ({ ...c, [k]: v }));
  const refreshStatus = async () => { try { setStatus(await api.status(court.id)); } catch {} };
  const refreshSnap = () => {
    setSnapLoading(true); setSnapErr(null);
    const url = api.snapshotUrl(court.id);
    const img = new Image();
    img.onload = () => { setSnapUrl(url); setSnapLoading(false); };
    img.onerror = () => { setSnapErr("Câmara inacessível"); setSnapLoading(false); };
    img.src = url;
  };
  useEffect(() => { refreshStatus(); refreshSnap(); const i = setInterval(refreshStatus, 5000); return () => clearInterval(i); }, []);

  const save = async () => { setBusy(true); try { setCourt(await api.updateCourt(court.id, court)); toast("Guardado"); } catch (e: any) { toast("Erro: " + e.message); } finally { setBusy(false); } };
  const start = async () => { setBusy(true); try { await api.updateCourt(court.id, court); await api.start(court.id); toast("Transmissão iniciada"); refreshStatus(); } catch (e: any) { toast("Erro: " + e.message); } finally { setBusy(false); } };
  const stop = async () => { setBusy(true); try { await api.stop(court.id); toast("Parada"); refreshStatus(); } catch (e: any) { toast("Erro: " + e.message); } finally { setBusy(false); } };
  const onLogo = async (f: File) => { try { const r = await api.uploadLogo(court.id, f); patch("logo_path", r.logo_path); toast("Logo carregado"); } catch (e: any) { toast("Erro: " + e.message); } };

  const running = status?.is_running;
  const logoUrl = court.logo_path ? `/data/${court.logo_path}?t=${court.id}` : null;

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <button onClick={onBack} className="flex items-center gap-2 text-slate-500 hover:text-slate-800 text-sm font-medium"><ArrowLeft className="h-4 w-4" /> Voltar</button>
        <span className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold ${running ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-500"}`}>
          <span className={`w-2 h-2 rounded-full ${running ? "bg-red-600 animate-pulse" : "bg-slate-400"}`} /> {running ? `LIVE · pid ${status?.pid}` : "OFFLINE"}
        </span>
      </div>
      <h1 className="text-2xl font-bold text-slate-800 mb-5 flex items-center gap-2"><Radio className="h-6 w-6 text-red-600" /> {court.name}</h1>

      <div className="grid lg:grid-cols-[1.7fr_1fr] gap-6 items-start">
        {/* PREVIEW GRANDE */}
        <div className="space-y-5">
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
            <LogoPositioner snapshotUrl={snapUrl} isLoadingSnapshot={snapLoading} snapshotError={snapErr}
              logoUrl={logoUrl} logoSizePercent={court.logo_size_percent} logoOpacity={court.logo_opacity}
              position={court.logo_position} cropRegion={court.crop_region ?? ""}
              onPositionChange={(p) => patch("logo_position", p)} onSizeChange={(s) => patch("logo_size_percent", s)} onRefresh={refreshSnap} />
          </div>
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
            <CropSelector snapshotUrl={snapUrl} isLoadingSnapshot={snapLoading} snapshotError={snapErr}
              cropRegion={court.crop_region ?? ""} onCropChange={(c) => patch("crop_region", c || null)} />
          </div>
        </div>

        {/* PAINEL CONFIG */}
        <div className="space-y-5">
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
            <h2 className="text-xs uppercase tracking-wide font-bold text-slate-500 mb-3">Transmissão</h2>
            {status?.last_error && <pre className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg p-2 whitespace-pre-wrap max-h-28 overflow-auto mb-3">{status.last_error.slice(-400)}</pre>}
            <div className="flex gap-2">
              {running ? <Button variant="stop" className="flex-1" onClick={stop} disabled={busy}><Square className="h-4 w-4" /> Parar</Button>
                : <Button variant="danger" className="flex-1" onClick={start} disabled={busy || !court.youtube_stream_key}><Play className="h-4 w-4" /> Iniciar</Button>}
            </div>
            {court.youtube_watch_url && <a href={court.youtube_watch_url} target="_blank" className="inline-flex items-center gap-1 text-sm text-blue-600 mt-3"><ExternalLink className="h-4 w-4" /> Ver no YouTube</a>}
          </div>

          <Card title="YouTube & Vídeo">
            <div className="flex items-center gap-2 mb-2">
              <input className="inp" placeholder="Stream key" value={court.youtube_stream_key ?? ""} onChange={(e) => patch("youtube_stream_key", e.target.value)} />
            </div>
            <Button variant="outline" size="sm" onClick={() => setShowCreate(true)}><Sparkles className="h-4 w-4 text-red-600" /> Criar transmissão automaticamente</Button>
            <div className="flex gap-3 mt-3">
              <Field label="Resolução"><select className="inp" value={court.resolution} onChange={(e) => patch("resolution", e.target.value)}>{RES.map((r) => <option key={r}>{r}</option>)}</select></Field>
              <Field label="Bitrate"><input type="number" className="inp" value={court.bitrate_kbps} onChange={(e) => patch("bitrate_kbps", +e.target.value)} /></Field>
              <Field label="FPS"><input type="number" className="inp" value={court.fps} onChange={(e) => patch("fps", +e.target.value)} /></Field>
            </div>
          </Card>

          <Card title="Logo">
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && onLogo(e.target.files[0])} />
            <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}><Upload className="h-4 w-4" /> Carregar logo</Button>
            <Field label={`Opacidade: ${court.logo_opacity}%`}><input type="range" min={10} max={100} step={5} className="w-full" value={court.logo_opacity} onChange={(e) => patch("logo_opacity", +e.target.value)} /></Field>
          </Card>

          <Card title="Texto e hora">
            <Field label="Texto fixo"><input className="inp" value={court.overlay_text ?? ""} onChange={(e) => patch("overlay_text", e.target.value)} /></Field>
            <label className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 mt-3 cursor-pointer">
              <span className="text-sm font-semibold text-slate-700 flex items-center gap-2"><Clock className="h-4 w-4" /> Hora actual</span>
              <input type="checkbox" checked={court.show_clock} onChange={(e) => patch("show_clock", e.target.checked)} />
            </label>
            <div className="flex gap-3 mt-3 flex-wrap">
              <Field label="Posição"><select className="inp" value={court.overlay_text_position} onChange={(e) => patch("overlay_text_position", e.target.value)}>{TEXT_POS.map((p) => <option key={p}>{p}</option>)}</select></Field>
              <Field label="Tamanho"><input type="number" className="inp" value={court.overlay_font_size} onChange={(e) => patch("overlay_font_size", +e.target.value)} /></Field>
              <Field label="Cor"><input type="color" className="inp h-10" value={(court.overlay_font_color || "#fff").startsWith("#") ? court.overlay_font_color : "#ffffff"} onChange={(e) => patch("overlay_font_color", e.target.value)} /></Field>
            </div>
          </Card>

          <Button onClick={save} disabled={busy} className="w-full"><Save className="h-4 w-4" /> Guardar configuração</Button>
        </div>
      </div>

      {showCreate && <CreateBroadcast court={court} onClose={() => setShowCreate(false)} onCreated={(key, watch) => { patch("youtube_stream_key", key); patch("youtube_watch_url", watch); toast("Transmissão criada"); }} />}
      {toastMsg && <Toast msg={toastMsg} />}
      <style>{`.inp{width:100%;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px;outline:none}.inp:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.12)}`}</style>
    </div>
  );
}

function CreateBroadcast({ court, onClose, onCreated }: { court: Court; onClose: () => void; onCreated: (key: string, watch: string) => void }) {
  const [title, setTitle] = useState(`Padel — ${court.name}`);
  const [privacy, setPrivacy] = useState("unlisted");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const go = async () => {
    setBusy(true); setErr("");
    try { const r = await api.createBroadcast(court.id, { title, privacy }); onCreated(r.stream_key, r.watch_url); onClose(); }
    catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-30" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h2 className="font-bold text-slate-800 flex items-center gap-2 mb-4"><Sparkles className="h-5 w-5 text-red-600" /> Criar transmissão YouTube</h2>
        <label className="block text-xs font-semibold text-slate-500 mb-1.5">Título</label>
        <input className="inp mb-3" value={title} onChange={(e) => setTitle(e.target.value)} />
        <label className="block text-xs font-semibold text-slate-500 mb-1.5">Privacidade</label>
        <select className="inp" value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
          <option value="public">Pública</option><option value="unlisted">Não listada</option><option value="private">Privada</option>
        </select>
        {err && <p className="text-red-600 text-xs mt-2">{err}</p>}
        <div className="flex gap-2 mt-5 justify-end">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button variant="danger" onClick={go} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Criar</Button>
        </div>
        <style>{`.inp{width:100%;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px;outline:none}`}</style>
      </div>
    </div>
  );
}

const Card: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5">
    <h2 className="text-xs uppercase tracking-wide font-bold text-slate-500 mb-3">{title}</h2>{children}
  </div>
);
const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex-1 min-w-[90px]"><label className="block text-xs font-semibold text-slate-500 mb-1.5">{label}</label>{children}</div>
);
const Toast: React.FC<{ msg: string }> = ({ msg }) => (
  <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-5 py-3 rounded-xl shadow-lg text-sm z-40">{msg}</div>
);
