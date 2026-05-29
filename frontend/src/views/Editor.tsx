import React, { useEffect, useRef, useState } from "react";
import { ArrowLeft, RotateCcw, Upload, Save, Play, Square, Maximize2, Sparkles, ExternalLink, Loader2, Crop as CropIcon, Type, Clock, Timer } from "lucide-react";
import { api, Court, StreamStatus } from "../api";
import { Button, Card, Badge } from "../ui";
import { LogoPositioner } from "../components/LogoPositioner";
import { CropSelector } from "../components/CropSelector";
import { OverlayText } from "../components/OverlayText";
import { FullscreenPreview } from "../components/FullscreenPreview";

const FONTS = ["Sans", "Serif", "Monospace", "DejaVu Sans", "DejaVu Serif", "Liberation Sans", "Noto Sans", "Impact"];
const TEXT_POS = ["TopLeft", "TopCenter", "TopRight", "BottomLeft", "BottomCenter", "BottomRight"];
const COLORS = ["#FFFFFF", "#000000", "#FFD400", "#FF3B30", "#34C759", "#0A84FF", "#FF9500", "#00E5FF"];

export default function Editor({ court: initial, onBack }: { court: Court; onBack: () => void }) {
  const [court, setCourt] = useState<Court>(initial);
  const [status, setStatus] = useState<StreamStatus | null>(null);
  const [snapUrl, setSnapUrl] = useState<string | null>(null);
  const [snapLoading, setSnapLoading] = useState(false);
  const [snapErr, setSnapErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [toast, setToast] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const t = (m: string) => { setToast(m); setTimeout(() => setToast(""), 2600); };

  const patch = (k: keyof Court, v: any) => setCourt((c) => ({ ...c, [k]: v }));
  const refreshStatus = async () => { try { setStatus(await api.status(court.id)); } catch {} };
  const refreshSnap = () => {
    setSnapLoading(true); setSnapErr(null);
    const url = api.snapshotUrl(court.id); const img = new Image();
    img.onload = () => { setSnapUrl(url); setSnapLoading(false); };
    img.onerror = () => { setSnapErr("Câmara inacessível"); setSnapLoading(false); };
    img.src = url;
  };
  useEffect(() => { refreshStatus(); refreshSnap(); const i = setInterval(refreshStatus, 5000); return () => clearInterval(i); }, []);

  const save = async () => { setBusy(true); try { setCourt(await api.updateCourt(court.id, court)); t("Guardado"); } catch (e: any) { t("Erro: " + e.message); } finally { setBusy(false); } };
  const start = async () => { setBusy(true); try { await api.updateCourt(court.id, court); await api.start(court.id); t("Iniciada"); refreshStatus(); } catch (e: any) { t("Erro: " + e.message); } finally { setBusy(false); } };
  const stop = async () => { setBusy(true); try { await api.stop(court.id); t("Parada"); refreshStatus(); } catch (e: any) { t("Erro: " + e.message); } finally { setBusy(false); } };
  const onLogo = async (f: File) => { try { const r = await api.uploadLogo(court.id, f); patch("logo_path", r.logo_path); t("Logo carregado"); } catch (e: any) { t("Erro: " + e.message); } };

  const running = status?.is_running;
  const logoUrl = court.logo_path ? `/data/${court.logo_path}?t=${court.id}` : null;

  return (
    <div className="p-8 max-w-[1500px] mx-auto">
      <div className="flex items-center justify-between mb-2">
        <button onClick={onBack} className="flex items-center gap-2 text-slate-400 hover:text-teal-400 text-sm"><ArrowLeft className="h-4 w-4" /> Voltar às transmissões</button>
        <div className="flex items-center gap-3">
          {running && <Badge tone="live">Em direto</Badge>}
          <Button variant="ghost" size="sm" onClick={() => setCourt(initial)}><RotateCcw className="h-4 w-4" /> Restaurar</Button>
        </div>
      </div>
      <h1 className="text-3xl font-extrabold text-white mb-1">Editor de transmissão</h1>
      <p className="text-slate-400 text-sm mb-6">Personalize a imagem da sua transmissão em direto — {court.name}.</p>

      <div className="grid lg:grid-cols-[1.8fr_1fr] gap-6 items-start">
        {/* Preview grande */}
        <div className="space-y-5">
          <Card className="p-5">
            <LogoPositioner snapshotUrl={snapUrl} isLoadingSnapshot={snapLoading} snapshotError={snapErr}
              logoUrl={logoUrl} logoSizePercent={court.logo_size_percent} logoOpacity={court.logo_opacity}
              position={court.logo_position} cropRegion={court.crop_region ?? ""}
              overlay={<OverlayText text={court.overlay_text} showClock={court.show_clock} position={court.overlay_text_position}
                fontSize={court.overlay_font_size} fontColor={court.overlay_font_color} fontFamily={court.overlay_font_family}
                bold={court.overlay_font_bold} italic={court.overlay_font_italic} bg={court.overlay_bg} />}
              onPositionChange={(p) => patch("logo_position", p)} onSizeChange={(s) => patch("logo_size_percent", s)} onRefresh={refreshSnap} />
            <div className="flex items-center justify-between mt-3">
              <span className="text-xs text-slate-500">Arraste os cantos do crop para ajustar · 16:9 · 1920×1080</span>
              <Button variant="outline" size="sm" onClick={() => setFullscreen(true)}><Maximize2 className="h-4 w-4" /> Ecrã inteiro</Button>
            </div>
          </Card>
          <Card className="p-5">
            <div className="flex items-center gap-2 mb-3 text-slate-300 text-sm font-semibold"><CropIcon className="h-4 w-4 text-teal-400" /> Recorte (crop)</div>
            <CropSelector snapshotUrl={snapUrl} isLoadingSnapshot={snapLoading} snapshotError={snapErr}
              cropRegion={court.crop_region ?? ""} onCropChange={(c) => patch("crop_region", c || null)} />
          </Card>
        </div>

        {/* Painel Elementos */}
        <div className="space-y-5">
          <Card className="p-5">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-bold text-white">Transmissão</span>
              <Badge tone={running ? "live" : court.youtube_stream_key ? "prep" : "off"}>{running ? `LIVE` : court.youtube_stream_key ? "Pronta" : "Sem key"}</Badge>
            </div>
            {status?.last_error && <pre className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-2 whitespace-pre-wrap max-h-24 overflow-auto mb-3">{status.last_error.slice(-400)}</pre>}
            <div className="flex gap-2">
              {running ? <Button variant="danger" className="flex-1" onClick={stop} disabled={busy}><Square className="h-4 w-4" /> Parar</Button>
                : <Button variant="teal" className="flex-1" onClick={start} disabled={busy || !court.youtube_stream_key}><Play className="h-4 w-4" /> Iniciar</Button>}
            </div>
            {court.youtube_watch_url && <a href={court.youtube_watch_url} target="_blank" className="inline-flex items-center gap-1 text-sm text-teal-400 mt-3"><ExternalLink className="h-4 w-4" /> Ver no YouTube</a>}
          </Card>

          <Card className="p-5 space-y-3">
            <div className="text-sm font-bold text-white">YouTube</div>
            <input className="inp" placeholder="Stream key" value={court.youtube_stream_key ?? ""} onChange={(e) => patch("youtube_stream_key", e.target.value)} />
            <Button variant="outline" size="sm" onClick={() => setShowCreate(true)}><Sparkles className="h-4 w-4 text-teal-400" /> Criar transmissão automaticamente</Button>
            <div className="flex gap-3">
              <Sel label="Resolução" value={court.resolution} opts={["720p", "1080p"]} onChange={(v) => patch("resolution", v)} />
              <Num label="Bitrate" value={court.bitrate_kbps} onChange={(v) => patch("bitrate_kbps", v)} />
              <Num label="FPS" value={court.fps} onChange={(v) => patch("fps", v)} />
            </div>
          </Card>

          <Card className="p-5 space-y-3">
            <div className="flex items-center justify-between"><div className="text-sm font-bold text-white flex items-center gap-2"><Upload className="h-4 w-4 text-teal-400" /> Logotipo</div></div>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && onLogo(e.target.files[0])} />
            <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()}><Upload className="h-4 w-4" /> Carregar logotipo</Button>
            <Range label={`Opacidade ${court.logo_opacity}%`} min={10} max={100} step={5} value={court.logo_opacity} onChange={(v) => patch("logo_opacity", v)} />
          </Card>

          <Card className="p-5 space-y-3">
            <div className="text-sm font-bold text-white flex items-center gap-2"><Type className="h-4 w-4 text-teal-400" /> Texto, hora & tempo</div>
            <input className="inp" placeholder="Texto fixo" value={court.overlay_text ?? ""} onChange={(e) => patch("overlay_text", e.target.value)} />
            <div className="flex gap-3">
              <Sel label="Tipo de letra" value={court.overlay_font_family} opts={FONTS} onChange={(v) => patch("overlay_font_family", v)} />
              <Sel label="Posição" value={court.overlay_text_position} opts={TEXT_POS} onChange={(v) => patch("overlay_text_position", v)} />
              <Num label="Tamanho" value={court.overlay_font_size} onChange={(v) => patch("overlay_font_size", v)} />
            </div>
            <div className="flex gap-2">
              <Tog active={court.overlay_font_bold} onClick={() => patch("overlay_font_bold", !court.overlay_font_bold)} label="B" bold />
              <Tog active={court.overlay_font_italic} onClick={() => patch("overlay_font_italic", !court.overlay_font_italic)} label="I" italic />
              <Tog active={court.overlay_bg} onClick={() => patch("overlay_bg", !court.overlay_bg)} label="Fundo" />
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {COLORS.map((c) => <button key={c} onClick={() => patch("overlay_font_color", c)} className={`w-6 h-6 rounded-full border-2 ${(court.overlay_font_color || "").toUpperCase() === c ? "border-teal-400 scale-110" : "border-slate-700"}`} style={{ background: c }} />)}
              <input type="color" className="w-8 h-8 rounded cursor-pointer bg-transparent" value={(court.overlay_font_color || "#fff").startsWith("#") ? court.overlay_font_color : "#ffffff"} onChange={(e) => patch("overlay_font_color", e.target.value)} />
            </div>
            <label className="flex items-center justify-between bg-slate-800/50 border border-slate-700 rounded-xl px-3 py-2.5 cursor-pointer">
              <span className="text-sm text-slate-300 flex items-center gap-2"><Clock className="h-4 w-4" /> Mostrar hora actual</span>
              <input type="checkbox" checked={court.show_clock} onChange={(e) => patch("show_clock", e.target.checked)} />
            </label>
          </Card>

          <Button variant="primary" onClick={save} disabled={busy} className="w-full"><Save className="h-4 w-4" /> Guardar e continuar</Button>
        </div>
      </div>

      {showCreate && <CreateBroadcast court={court} onClose={() => setShowCreate(false)} onCreated={(key, watch) => { patch("youtube_stream_key", key); patch("youtube_watch_url", watch); t("Transmissão criada"); }} />}
      {fullscreen && <FullscreenPreview court={court} snapshotUrl={snapUrl} onClose={() => setFullscreen(false)} />}
      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-800 border border-slate-700 text-white px-5 py-3 rounded-xl text-sm z-40">{toast}</div>}
    </div>
  );
}

const Sel: React.FC<{ label: string; value: string; opts: string[]; onChange: (v: string) => void }> = ({ label, value, opts, onChange }) => (
  <div className="flex-1 min-w-[90px]"><label className="block text-xs text-slate-500 mb-1.5">{label}</label><select className="inp" value={value} onChange={(e) => onChange(e.target.value)}>{opts.map((o) => <option key={o} className="bg-slate-900">{o}</option>)}</select></div>
);
const Num: React.FC<{ label: string; value: number; onChange: (v: number) => void }> = ({ label, value, onChange }) => (
  <div className="flex-1 min-w-[70px]"><label className="block text-xs text-slate-500 mb-1.5">{label}</label><input type="number" className="inp" value={value} onChange={(e) => onChange(+e.target.value)} /></div>
);
const Range: React.FC<{ label: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void }> = ({ label, min, max, step, value, onChange }) => (
  <div><label className="block text-xs text-slate-500 mb-1.5">{label}</label><input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(+e.target.value)} className="w-full accent-teal-400" /></div>
);
const Tog: React.FC<{ active: boolean; onClick: () => void; label: string; bold?: boolean; italic?: boolean }> = ({ active, onClick, label, bold, italic }) => (
  <button onClick={onClick} className={`px-3 py-2 rounded-lg border text-sm ${active ? "bg-teal-500 text-slate-900 border-teal-500" : "bg-slate-800/50 border-slate-700 text-slate-300"} ${bold ? "font-bold" : ""} ${italic ? "italic" : ""}`}>{label}</button>
);

function CreateBroadcast({ court, onClose, onCreated }: { court: Court; onClose: () => void; onCreated: (key: string, watch: string) => void }) {
  const [title, setTitle] = useState(`Padel — ${court.name}`);
  const [privacy, setPrivacy] = useState("unlisted");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const go = async () => { setBusy(true); setErr(""); try { const r = await api.createBroadcast(court.id, { title, privacy }); onCreated(r.stream_key, r.watch_url); onClose(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } };
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50" onClick={onClose}>
      <Card className="p-6 w-full max-w-md bg-slate-900" >
        <div onClick={(e) => e.stopPropagation()}>
          <h2 className="font-bold text-white flex items-center gap-2 mb-4"><Sparkles className="h-5 w-5 text-teal-400" /> Criar transmissão YouTube</h2>
          <label className="block text-xs text-slate-500 mb-1.5">Título</label>
          <input className="inp mb-3" value={title} onChange={(e) => setTitle(e.target.value)} />
          <label className="block text-xs text-slate-500 mb-1.5">Privacidade</label>
          <select className="inp" value={privacy} onChange={(e) => setPrivacy(e.target.value)}><option value="public" className="bg-slate-900">Pública</option><option value="unlisted" className="bg-slate-900">Não listada</option><option value="private" className="bg-slate-900">Privada</option></select>
          {err && <p className="text-red-400 text-xs mt-2">{err}</p>}
          <div className="flex gap-2 mt-5 justify-end">
            <Button variant="ghost" onClick={onClose}>Cancelar</Button>
            <Button variant="teal" onClick={go} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Criar</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
