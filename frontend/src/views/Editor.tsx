import React, { useEffect, useRef, useState } from "react";
import {
  ArrowLeft, RotateCcw, Upload, Crop as CropIcon, ZoomIn, Move, ArrowUp, ArrowDown, ArrowRight, ArrowLeft as AL,
  Image as ImageIcon, Type, Clock, Timer, Eye, RefreshCw, Play, Square, Sparkles, ExternalLink, Loader2, Plus, Minus,
} from "lucide-react";
import { api, Court, StreamStatus } from "../api";
import { Button, Card } from "../ui";
import { FullscreenPreview } from "../components/FullscreenPreview";
import { EditorCanvas } from "../components/EditorCanvas";

const FONTS = ["Sans", "Serif", "Monospace", "DejaVu Sans", "DejaVu Serif", "Liberation Sans", "Noto Sans", "Impact"];

export default function Editor({ court: initial, onBack }: { court: Court; onBack: () => void }) {
  const [court, setCourt] = useState<Court>(initial);
  const [status, setStatus] = useState<StreamStatus | null>(null);
  const [snapUrl, setSnapUrl] = useState<string | null>(null);
  const [snapErr, setSnapErr] = useState(false);
  const [tab, setTab] = useState<"elementos" | "camadas">("elementos");
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [now, setNow] = useState(new Date());
  const [toast, setToast] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const t = (m: string) => { setToast(m); setTimeout(() => setToast(""), 2400); };
  const patch = (k: keyof Court, v: any) => setCourt((c) => ({ ...c, [k]: v }));

  const refreshSnap = () => {
    const url = api.snapshotUrl(court.id); const img = new Image();
    img.onload = () => { setSnapUrl(url); setSnapErr(false); };
    img.onerror = () => setSnapErr(true);
    img.src = url;
  };
  useEffect(() => { refreshSnap(); api.status(court.id).then(setStatus).catch(() => {}); }, []);
  useEffect(() => { const i = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(i); }, []);

  const save = async () => { setBusy(true); try { setCourt(await api.updateCourt(court.id, court)); t("Guardado"); } catch (e: any) { t("Erro: " + e.message); } finally { setBusy(false); } };
  const onLogo = async (f: File) => { try { const r = await api.uploadLogo(court.id, f); patch("logo_path", r.logo_path); t("Logo carregado"); } catch (e: any) { t("Erro: " + e.message); } };

  const clock = now.toLocaleTimeString("pt-PT", { hour12: court.clock_format === "12h", hour: "2-digit", minute: "2-digit" });
  const timerSample = court.timer_format === "MM:SS" ? "45:18" : "00:45:18";
  const logoUrl = court.logo_path ? `/data/${court.logo_path}?t=${court.id}` : null;
  const cropStyle = cropCss(court.crop_region);

  return (
    <div className="p-8 max-w-[1500px] mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-3xl font-extrabold text-white">Editor de transmissão</h1>
          <p className="text-slate-400 text-sm mt-1">Personalize a imagem da sua transmissão em directo.</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={onBack}><ArrowLeft className="h-4 w-4" /> Voltar às transmissões</Button>
          <Button variant="outline" size="sm" onClick={() => setCourt(initial)}><RotateCcw className="h-4 w-4" /> Restaurar predefinições</Button>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1.75fr_1fr] gap-6 items-start">
        {/* PREVIEW */}
        <div>
          <EditorCanvas court={court} snapshotUrl={snapErr ? null : snapUrl} patch={patch} />
          <div className="flex items-center justify-between mt-3 text-xs text-slate-500">
            <span>ⓘ Dica: arraste os cantos ou as bordas para ajustar o recorte da imagem.</span>
            <div className="flex items-center gap-2">
              <span className="px-2 py-1 rounded bg-slate-800 border border-slate-700">16:9</span>
              <span className="px-2 py-1 rounded bg-slate-800 border border-slate-700">1920 × 1080</span>
            </div>
          </div>

          <div className="flex items-center gap-3 mt-5">
            <Button variant="outline" onClick={() => setFullscreen(true)}><Eye className="h-4 w-4" /> Pré-visualizar</Button>
            <Button variant="primary" onClick={save} disabled={busy} className="flex-1">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Guardar e continuar <ArrowRight className="h-4 w-4" /></Button>
          </div>
        </div>

        {/* PAINEL ELEMENTOS */}
        <Card className="p-0 overflow-hidden">
          <div className="flex border-b border-slate-800">
            {(["elementos", "camadas"] as const).map((tb) => (
              <button key={tb} onClick={() => setTab(tb)} className={`flex-1 py-3.5 text-sm font-semibold capitalize ${tab === tb ? "text-teal-400 border-b-2 border-teal-400" : "text-slate-500"}`}>{tb}</button>
            ))}
          </div>

          {tab === "camadas" ? (
            <div className="p-5 text-sm text-slate-500">Camadas: logótipo, texto, hora e cronómetro sobrepõem-se por esta ordem.</div>
          ) : (
            <div className="p-5 space-y-5">
              {/* Crop */}
              <Row icon={CropIcon} label="Crop"><Button variant="outline" size="sm" onClick={() => patch("crop_region", null)}>Ajustar ao ecrã</Button></Row>
              {/* Zoom */}
              <div className="flex items-center gap-3"><RowLabel icon={ZoomIn} label="Zoom" /><input type="range" min={50} max={200} defaultValue={100} className="flex-1 accent-teal-400" /><span className="text-xs text-slate-300 w-12 text-right">100%</span></div>
              {/* Posição */}
              <div className="flex items-center gap-2"><RowLabel icon={Move} label="Posição" /><div className="flex gap-1 ml-auto">{[ArrowUp, ArrowDown, AL, ArrowRight].map((I, i) => <button key={i} className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 hover:border-teal-500/40"><I className="h-4 w-4" /></button>)}<button className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300"><RotateCcw className="h-4 w-4" /></button></div></div>

              <div className="border-t border-slate-800" />

              {/* Logótipo */}
              <Row icon={ImageIcon} label="Logótipo"><Toggle v={court.show_logo} on={(b) => patch("show_logo", b)} /></Row>
              {court.show_logo && <>
                <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && onLogo(e.target.files[0])} />
                <button onClick={() => fileRef.current?.click()} className="w-full py-4 rounded-xl border border-dashed border-slate-700 text-slate-400 hover:border-teal-500/40 flex flex-col items-center gap-1">
                  <Upload className="h-5 w-5" /><span className="text-sm font-medium">Carregar logótipo</span><span className="text-[11px] text-slate-600">PNG, JPG ou SVG (máx. 2MB)</span>
                </button>
              </>}

              {/* Texto */}
              <Row icon={Type} label="Texto"><div className="flex items-center gap-2 ml-auto"><input className="inp py-2 w-44" value={court.overlay_text ?? ""} onChange={(e) => patch("overlay_text", e.target.value)} /><Toggle v={court.show_text} on={(b) => patch("show_text", b)} /></div></Row>
              {court.show_text && <>
                <Field label="Tipo de letra"><select className="inp" value={court.overlay_font_family} onChange={(e) => patch("overlay_font_family", e.target.value)}>{FONTS.map((f) => <option key={f} className="bg-slate-900">{f}</option>)}</select></Field>
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Tamanho"><Stepper v={court.overlay_font_size} on={(n) => patch("overlay_font_size", n)} /></Field>
                  <Field label="Cor"><Swatch v={court.overlay_font_color} on={(c) => patch("overlay_font_color", c)} /></Field>
                  <Field label="Fundo do texto"><Swatch v={court.text_bg_color} on={(c) => patch("text_bg_color", c)} /></Field>
                </div>
                <Field label={`Opacidade ${court.overlay_opacity}%`}><input type="range" min={10} max={100} step={5} value={court.overlay_opacity} onChange={(e) => patch("overlay_opacity", +e.target.value)} className="w-full accent-teal-400" /></Field>
              </>}

              <div className="border-t border-slate-800" />

              {/* Hora */}
              <Row icon={Clock} label="Hora"><Toggle v={court.show_clock} on={(b) => patch("show_clock", b)} /></Row>
              {court.show_clock && (
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Formato"><select className="inp" value={court.clock_format} onChange={(e) => patch("clock_format", e.target.value)}><option value="24h" className="bg-slate-900">24 horas</option><option value="12h" className="bg-slate-900">12 horas</option></select></Field>
                  <Field label="Cor"><Swatch v={court.clock_color} on={(c) => patch("clock_color", c)} /></Field>
                  <Field label="Fundo"><Swatch v={court.clock_bg} on={(c) => patch("clock_bg", c)} /></Field>
                </div>
              )}
              {/* Tempo */}
              <Row icon={Timer} label="Tempo"><Toggle v={court.show_timer} on={(b) => patch("show_timer", b)} /></Row>
              {court.show_timer && (
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Formato"><select className="inp" value={court.timer_format} onChange={(e) => patch("timer_format", e.target.value)}><option value="HH:MM:SS" className="bg-slate-900">HH:MM:SS</option><option value="MM:SS" className="bg-slate-900">MM:SS</option></select></Field>
                  <Field label="Cor"><Swatch v={court.timer_color} on={(c) => patch("timer_color", c)} /></Field>
                  <Field label="Fundo"><Swatch v={court.timer_bg} on={(c) => patch("timer_bg", c)} /></Field>
                </div>
              )}

              <div className="border-t border-slate-800" />

              {/* YouTube */}
              <Field label="Stream key do YouTube"><input className="inp" placeholder="xxxx-xxxx-xxxx" value={court.youtube_stream_key ?? ""} onChange={(e) => patch("youtube_stream_key", e.target.value)} /></Field>
              <Button variant="outline" size="sm" onClick={() => setShowCreate(true)} className="w-full"><Sparkles className="h-4 w-4 text-teal-400" /> Criar transmissão automaticamente</Button>
              {status?.is_running
                ? <Button variant="danger" className="w-full" onClick={async () => { await api.stop(court.id); api.status(court.id).then(setStatus); }}><Square className="h-4 w-4" /> Parar transmissão</Button>
                : <Button variant="teal" className="w-full" disabled={!court.youtube_stream_key} onClick={async () => { await api.updateCourt(court.id, court); await api.start(court.id); api.status(court.id).then(setStatus); t("Iniciada"); }}><Play className="h-4 w-4" /> Iniciar transmissão</Button>}
              {court.youtube_watch_url && <a href={court.youtube_watch_url} target="_blank" className="flex items-center justify-center gap-1 text-sm text-teal-400"><ExternalLink className="h-4 w-4" /> Ver no YouTube</a>}
            </div>
          )}
        </Card>
      </div>

      {showCreate && <CreateBroadcast court={court} onClose={() => setShowCreate(false)} onCreated={(key, watch) => { patch("youtube_stream_key", key); patch("youtube_watch_url", watch); t("Transmissão criada"); }} />}
      {fullscreen && <FullscreenPreview court={court} snapshotUrl={snapUrl} onClose={() => setFullscreen(false)} />}
      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-800 border border-slate-700 text-white px-5 py-3 rounded-xl text-sm z-40">{toast}</div>}
    </div>
  );
}

const RowLabel: React.FC<{ icon: any; label: string }> = ({ icon: Icon, label }) => (
  <span className="flex items-center gap-2 text-sm font-medium text-slate-300"><Icon className="h-4 w-4 text-slate-500" /> {label}</span>
);
const Row: React.FC<{ icon: any; label: string; children: React.ReactNode }> = ({ icon, label, children }) => (
  <div className="flex items-center justify-between gap-2"><RowLabel icon={icon} label={label} /><div className="ml-auto">{children}</div></div>
);
const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div><label className="block text-xs text-slate-500 mb-1.5">{label}</label>{children}</div>
);
const Toggle: React.FC<{ v: boolean; on: (b: boolean) => void }> = ({ v, on }) => (
  <button onClick={() => on(!v)} className={`relative w-11 h-6 rounded-full transition ${v ? "bg-teal-500" : "bg-slate-700"}`}>
    <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition ${v ? "left-[22px]" : "left-0.5"}`} />
  </button>
);
const Stepper: React.FC<{ v: number; on: (n: number) => void }> = ({ v, on }) => (
  <div className="flex items-center border border-slate-700 rounded-lg overflow-hidden">
    <button onClick={() => on(Math.max(8, v - 2))} className="px-2 py-2 text-slate-400 hover:bg-slate-800"><Minus className="h-3.5 w-3.5" /></button>
    <span className="flex-1 text-center text-sm text-white">{v}</span>
    <button onClick={() => on(Math.min(120, v + 2))} className="px-2 py-2 text-slate-400 hover:bg-slate-800"><Plus className="h-3.5 w-3.5" /></button>
  </div>
);
const Swatch: React.FC<{ v: string; on: (c: string) => void }> = ({ v, on }) => (
  <div className="flex items-center gap-2 border border-slate-700 rounded-lg px-2 py-1.5">
    <input type="color" value={(v || "#fff").startsWith("#") ? v : "#ffffff"} onChange={(e) => on(e.target.value)} className="w-6 h-6 rounded cursor-pointer bg-transparent" />
    <span className="text-xs text-slate-400 font-mono truncate">{v}</span>
  </div>
);

/** Devolve a cor como-está (CSS aceita #RRGGBB e #RRGGBBAA). Fallback semi-transparente. */
function hexa(c?: string): string {
  if (!c) return "rgba(0,0,0,0.5)";
  return c;
}

function cropCss(cropRegion?: string | null): React.CSSProperties {
  if (!cropRegion) return { inset: 0, width: "100%", height: "100%", objectFit: "contain" };
  const p = cropRegion.split(",").map((v) => parseFloat(v));
  if (p.length !== 4 || p.some((v) => isNaN(v))) return { inset: 0, width: "100%", height: "100%", objectFit: "contain" };
  const [x, y, w, h] = p;
  if (w <= 0 || h <= 0) return { inset: 0, width: "100%", height: "100%", objectFit: "contain" };
  return { left: `-${(x * 100 / w).toFixed(2)}%`, top: `-${(y * 100 / h).toFixed(2)}%`, width: `${(100 * 100 / w).toFixed(2)}%`, height: `${(100 * 100 / h).toFixed(2)}%`, objectFit: "fill", maxWidth: "none", maxHeight: "none" };
}

function CreateBroadcast({ court, onClose, onCreated }: { court: Court; onClose: () => void; onCreated: (key: string, watch: string) => void }) {
  const [title, setTitle] = useState(`Padel — ${court.name}`);
  const [privacy, setPrivacy] = useState("unlisted");
  const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const go = async () => { setBusy(true); setErr(""); try { const r = await api.createBroadcast(court.id, { title, privacy }); onCreated(r.stream_key, r.watch_url); onClose(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } };
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <h2 className="font-bold text-white flex items-center gap-2 mb-4"><Sparkles className="h-5 w-5 text-teal-400" /> Criar transmissão YouTube</h2>
        <label className="block text-xs text-slate-500 mb-1.5">Título</label>
        <input className="inp mb-3" value={title} onChange={(e) => setTitle(e.target.value)} />
        <label className="block text-xs text-slate-500 mb-1.5">Privacidade</label>
        <select className="inp" value={privacy} onChange={(e) => setPrivacy(e.target.value)}><option value="public" className="bg-slate-900">Pública</option><option value="unlisted" className="bg-slate-900">Não listada</option><option value="private" className="bg-slate-900">Privada</option></select>
        {err && <p className="text-red-400 text-xs mt-2">{err}</p>}
        <div className="flex gap-2 mt-5 justify-end"><Button variant="ghost" onClick={onClose}>Cancelar</Button><Button variant="teal" onClick={go} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Criar</Button></div>
      </div>
    </div>
  );
}
