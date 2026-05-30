import React, { useEffect, useRef, useState } from "react";
import {
  ArrowLeft, RotateCcw, Upload, Crop as CropIcon, ZoomIn, Move, ArrowUp, ArrowDown, ArrowRight, ArrowLeft as AL,
  Image as ImageIcon, Type, Clock, Timer, Eye, RefreshCw, Play, Square, Sparkles, ExternalLink, Loader2, Plus, Minus,
  Volume2, Headphones, CalendarClock,
} from "lucide-react";

const DIAS = [["Seg", 0], ["Ter", 1], ["Qua", 2], ["Qui", 3], ["Sex", 4], ["Sáb", 5], ["Dom", 6]] as const;
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
  const [toast, setToast] = useState("");
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const thumbRef = useRef<HTMLInputElement>(null);
  const t = (m: string) => { setToast(m); setTimeout(() => setToast(""), 2400); };
  const patch = (k: keyof Court, v: any) => setCourt((c) => ({ ...c, [k]: v }));

  // ── Crop helpers (Zoom + Posição actuam sobre o crop) ──
  const cropRect = () => {
    const p = (court.crop_region || "").split(",").map(Number);
    return p.length === 4 && !p.some(isNaN) ? { x: p[0], y: p[1], w: p[2], h: p[3] } : { x: 0, y: 0, w: 100, h: 100 };
  };
  const setCrop = (r: { x: number; y: number; w: number; h: number }) =>
    patch("crop_region", `${r.x.toFixed(1)},${r.y.toFixed(1)},${r.w.toFixed(1)},${r.h.toFixed(1)}`);
  const zoomVal = Math.round(10000 / (cropRect().w || 100));   // 100% = sem zoom
  const applyZoom = (z: number) => {
    const size = Math.max(25, Math.min(100, 10000 / z));
    const off = (100 - size) / 2;
    if (z <= 100) { patch("crop_region", null); return; }       // 100% = frame inteiro
    setCrop({ x: off, y: off, w: size, h: size });
  };
  const nudge = (dx: number, dy: number) => {
    const r = cropRect();
    setCrop({ x: Math.max(0, Math.min(100 - r.w, r.x + dx)), y: Math.max(0, Math.min(100 - r.h, r.y + dy)), w: r.w, h: r.h });
  };

  const refreshSnap = () => {
    const url = api.snapshotUrl(court.id); const img = new Image();
    img.onload = () => { setSnapUrl(url); setSnapErr(false); };
    img.onerror = () => setSnapErr(true);
    img.src = url;
  };
  useEffect(() => { refreshSnap(); api.status(court.id).then(setStatus).catch(() => {}); }, []);

  const save = async () => { setBusy(true); try { setCourt(await api.updateCourt(court.id, court)); t("Guardado"); } catch (e: any) { t("Erro: " + e.message); } finally { setBusy(false); } };
  const onLogo = async (f: File) => { try { const r = await api.uploadLogo(court.id, f); patch("logo_path", r.logo_path); t("Logo carregado"); } catch (e: any) { t("Erro: " + e.message); } };
  const onThumb = async (f: File) => { try { const r = await api.uploadThumbnail(court.id, f); patch("thumbnail_path", r.thumbnail_path); t(r.warning ? "Miniatura guardada — " + r.warning : (r.applied ? "Miniatura aplicada no YouTube" : "Miniatura guardada")); } catch (e: any) { t("Erro: " + e.message); } };
  const applyThumb = async () => { try { await api.applyThumbnail(court.id); t("Miniatura aplicada no YouTube"); } catch (e: any) { t("Erro: " + e.message); } };
  // Guarda primeiro (para o teste usar o volume atual), depois captura 6s e toca.
  const testAudio = async () => { setBusy(true); try { await api.updateCourt(court.id, court); const url = await api.audioTest(court.id); setAudioUrl(url); t("Áudio capturado"); } catch (e: any) { t("Erro: " + e.message); } finally { setBusy(false); } };


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
            <div className="p-5 space-y-2">
              <p className="text-xs text-slate-500 mb-3">Activa/desactiva cada camada. São compostas por esta ordem (logótipo em cima).</p>
              {([
                ["Logótipo", "show_logo", ImageIcon],
                ["Texto", "show_text", Type],
                ["Hora", "show_clock", Clock],
                ["Cronómetro", "show_timer", Timer],
                ["Som da câmara", "audio_enabled", Volume2],
              ] as const).map(([label, key, Icon]) => (
                <div key={key} className="flex items-center justify-between px-3 py-3 rounded-xl bg-slate-800/40 border border-slate-800">
                  <span className="flex items-center gap-2 text-sm text-slate-200"><Icon className="h-4 w-4 text-teal-400" /> {label}</span>
                  <Toggle v={(court as any)[key]} on={(b) => patch(key as keyof Court, b)} />
                </div>
              ))}
            </div>
          ) : (
            <div className="p-5 space-y-5">
              {/* Crop */}
              <Row icon={CropIcon} label="Crop"><Button variant="outline" size="sm" onClick={() => patch("crop_region", null)}>Ajustar ao ecrã</Button></Row>
              {/* Zoom */}
              <div className="flex items-center gap-3"><RowLabel icon={ZoomIn} label="Zoom" /><input type="range" min={100} max={300} value={zoomVal} onChange={(e) => applyZoom(+e.target.value)} className="flex-1 accent-teal-400" /><span className="text-xs text-slate-300 w-12 text-right">{zoomVal}%</span></div>
              {/* Posição */}
              <div className="flex items-center gap-2"><RowLabel icon={Move} label="Posição" /><div className="flex gap-1 ml-auto">
                <button onClick={() => nudge(0, -3)} className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 hover:border-teal-500/40"><ArrowUp className="h-4 w-4" /></button>
                <button onClick={() => nudge(0, 3)} className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 hover:border-teal-500/40"><ArrowDown className="h-4 w-4" /></button>
                <button onClick={() => nudge(-3, 0)} className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 hover:border-teal-500/40"><AL className="h-4 w-4" /></button>
                <button onClick={() => nudge(3, 0)} className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 hover:border-teal-500/40"><ArrowRight className="h-4 w-4" /></button>
                <button onClick={() => patch("crop_region", null)} className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 hover:border-teal-500/40"><RotateCcw className="h-4 w-4" /></button>
              </div></div>

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

              {/* Áudio */}
              <Row icon={Volume2} label="Som da câmara"><Toggle v={court.audio_enabled} on={(b) => patch("audio_enabled", b)} /></Row>
              {court.audio_enabled && <>
                <Field label={`Volume enviado para o YouTube — ${Math.round((court.audio_volume ?? 1) * 100)}%`}>
                  <input type="range" min={0} max={200} step={5} value={Math.round((court.audio_volume ?? 1) * 100)} onChange={(e) => patch("audio_volume", +e.target.value / 100)} className="w-full accent-teal-400" />
                </Field>
                <Row icon={Sparkles} label="Reduzir ruído (ventoinhas)"><Toggle v={court.audio_denoise} on={(b) => patch("audio_denoise", b)} /></Row>
                {court.audio_denoise && (
                  <Field label={`Intensidade da redução — ${court.audio_denoise_strength}`}>
                    <input type="range" min={5} max={30} step={1} value={court.audio_denoise_strength} onChange={(e) => patch("audio_denoise_strength", +e.target.value)} className="w-full accent-teal-400" />
                  </Field>
                )}
                <Button variant="outline" size="sm" onClick={testAudio} disabled={busy} className="w-full">
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Headphones className="h-4 w-4 text-teal-400" />} Testar / Ouvir (6s)
                </Button>
                {audioUrl && <audio controls autoPlay src={audioUrl} className="w-full mt-1" />}
                <p className="text-[11px] text-slate-600">Ouves aqui exactamente o que vai para o YouTube (já com a redução de ruído). Ajusta a intensidade e volta a testar.</p>
              </>}

              <div className="border-t border-slate-800" />

              {/* YouTube */}
              <Field label="Stream key do YouTube"><input className="inp" placeholder="xxxx-xxxx-xxxx" value={court.youtube_stream_key ?? ""} onChange={(e) => patch("youtube_stream_key", e.target.value)} /></Field>

              {/* Miniatura (capa do YouTube) */}
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">Miniatura (capa no YouTube)</label>
                <input ref={thumbRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && onThumb(e.target.files[0])} />
                {court.thumbnail_path ? (
                  <div className="space-y-2">
                    <img src={`/data/${court.thumbnail_path}?t=${court.id}`} alt="miniatura" className="w-full rounded-lg border border-slate-700 aspect-video object-cover" />
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => thumbRef.current?.click()} className="flex-1"><Upload className="h-4 w-4" /> Trocar imagem</Button>
                      <Button variant="outline" size="sm" onClick={applyThumb} disabled={!court.youtube_broadcast_id} className="flex-1"><ImageIcon className="h-4 w-4 text-teal-400" /> Aplicar ao YouTube</Button>
                    </div>
                  </div>
                ) : (
                  <button onClick={() => thumbRef.current?.click()} className="w-full py-4 rounded-xl border border-dashed border-slate-700 text-slate-400 hover:border-teal-500/40 flex flex-col items-center gap-1">
                    <ImageIcon className="h-5 w-5" /><span className="text-sm font-medium">Carregar miniatura</span><span className="text-[11px] text-slate-600">16:9 — fica 1280×720, JPG/PNG</span>
                  </button>
                )}
                <p className="text-[11px] text-slate-600 mt-1">Substitui a tua foto de perfil na lista do YouTube. É aplicada ao criar a transmissão; com transmissão já criada usa “Aplicar ao YouTube”.</p>
              </div>

              <Button variant="outline" size="sm" onClick={() => setShowCreate(true)} className="w-full"><Sparkles className="h-4 w-4 text-teal-400" /> Criar transmissão automaticamente</Button>
              {status?.is_running
                ? <Button variant="danger" className="w-full" onClick={async () => { await api.stop(court.id); api.status(court.id).then(setStatus); }}><Square className="h-4 w-4" /> Parar transmissão</Button>
                : <Button variant="teal" className="w-full" disabled={!court.youtube_stream_key} onClick={async () => { await api.updateCourt(court.id, court); await api.start(court.id); api.status(court.id).then(setStatus); t("Iniciada"); }}><Play className="h-4 w-4" /> Iniciar transmissão</Button>}
              {court.youtube_watch_url && <a href={court.youtube_watch_url} target="_blank" className="flex items-center justify-center gap-1 text-sm text-teal-400"><ExternalLink className="h-4 w-4" /> Ver no YouTube</a>}

              <div className="border-t border-slate-800" />

              {/* Agendamento automático */}
              <Row icon={CalendarClock} label="Agendar automaticamente"><Toggle v={court.schedule_enabled} on={(b) => patch("schedule_enabled", b)} /></Row>
              {court.schedule_enabled && <>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Início"><input type="time" className="inp" value={court.schedule_start || "09:00"} onChange={(e) => patch("schedule_start", e.target.value)} /></Field>
                  <Field label="Fim"><input type="time" className="inp" value={court.schedule_end || "22:00"} onChange={(e) => patch("schedule_end", e.target.value)} /></Field>
                </div>
                <div>
                  <label className="block text-xs text-slate-500 mb-1.5">Dias (vazio = todos)</label>
                  <div className="flex gap-1">
                    {DIAS.map(([lbl, d]) => {
                      const sel = (court.schedule_days || "").split(",").filter(Boolean).map(Number);
                      const on = sel.includes(d);
                      return (
                        <button key={d} onClick={() => {
                          const next = on ? sel.filter((x) => x !== d) : [...sel, d];
                          next.sort((a, b) => a - b);
                          patch("schedule_days", next.join(","));
                        }} className={`flex-1 py-1.5 rounded-lg text-xs font-medium border ${on ? "bg-teal-500 text-slate-900 border-teal-500" : "bg-slate-800 text-slate-400 border-slate-700"}`}>{lbl}</button>
                      );
                    })}
                  </div>
                </div>
                <p className="text-[11px] text-slate-600">A transmissão liga/desliga sozinha dentro do horário (hora do Jetson). Precisa de stream key. Guarda para aplicar.</p>
              </>}
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
