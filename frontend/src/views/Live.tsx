import React, { useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, Square, RotateCw, Pause, MonitorPlay, Activity, Gauge, Clock, Youtube, Camera, Wifi, AudioLines } from "lucide-react";
import { api, Court, StreamStatus } from "../api";
import { Button, Card, Badge } from "../ui";

export default function Live({ court: initial, onBack }: { court: Court; onBack: () => void }) {
  const [court, setCourt] = useState<Court>(initial);
  const [status, setStatus] = useState<StreamStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => { try { setStatus(await api.status(court.id)); } catch {} };
  useEffect(() => { refresh(); const i = setInterval(refresh, 4000); return () => clearInterval(i); }, []);

  const patchToggle = async (k: keyof Court, v: boolean) => {
    setCourt((c) => ({ ...c, [k]: v }));
    try { await api.updateCourt(court.id, { [k]: v } as any); } catch {}
  };
  const stop = async () => { setBusy(true); try { await api.stop(court.id); await refresh(); } finally { setBusy(false); } };
  const restart = async () => { setBusy(true); try { await api.stop(court.id); await api.start(court.id); await refresh(); } catch {} finally { setBusy(false); } };

  const running = status?.is_running;
  const up = uptime(status?.started_at);

  const metrics = [
    { icon: MonitorPlay, label: "QUALIDADE", value: court.resolution, sub: "config", color: "#2dd4bf" },
    { icon: Gauge, label: "BITRATE", value: `${(court.bitrate_kbps / 1000).toFixed(1)} Mbps`, sub: "alvo", color: "#3b82f6" },
    { icon: Activity, label: "FPS", value: `${court.fps}`, sub: "alvo", color: "#22c55e" },
    { icon: Clock, label: "TEMPO LIVE", value: running ? up : "—", sub: running ? "em direto" : "parado", color: "#a855f7" },
    { icon: Youtube, label: "YOUTUBE", value: court.youtube_watch_url ? "Ligado" : "—", sub: court.youtube_broadcast_id ? "broadcast" : "sem live", color: "#ef4444" },
    { icon: Camera, label: "CÂMARA", value: court.name, sub: court.camera_ip, color: "#06b6d4" },
    { icon: Wifi, label: "PARAGENS", value: String(status?.restart_count ?? 0), sub: "restarts", color: "#f59e0b" },
    { icon: AudioLines, label: "ÁUDIO", value: "Activo", sub: "silêncio", color: "#14b8a6" },
  ];

  return (
    <div className="p-8 max-w-[1500px] mx-auto">
      <div className="flex items-center justify-between mb-2">
        <button onClick={onBack} className="flex items-center gap-2 text-slate-400 hover:text-teal-400 text-sm"><ArrowLeft className="h-4 w-4" /> Voltar</button>
        {court.youtube_watch_url && <a href={court.youtube_watch_url} target="_blank"><Button variant="outline" size="sm"><ExternalLink className="h-4 w-4" /> Ver página pública</Button></a>}
      </div>
      <h1 className="text-3xl font-extrabold text-white flex items-center gap-3 mb-1">
        <span className={`w-3 h-3 rounded-full ${running ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} /> Live em curso
      </h1>
      <p className="text-slate-400 text-sm mb-6">Acompanhe e controle a transmissão de {court.name}.</p>

      <div className="grid lg:grid-cols-[1.6fr_1fr_280px] gap-6 items-start">
        {/* Player */}
        <Card className="overflow-hidden">
          <div className="relative aspect-video bg-black">
            <img src={api.snapshotUrl(court.id)} alt="" className="w-full h-full object-cover" onError={(e) => ((e.currentTarget as HTMLImageElement).style.opacity = "0")} />
            {running && <span className="absolute top-3 left-3"><Badge tone="live">LIVE · {up}</Badge></span>}
            <div className="absolute bottom-3 left-3 text-white font-bold text-lg drop-shadow">{court.name}</div>
          </div>
        </Card>

        {/* Estado */}
        <Card className="p-5">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-bold tracking-wide text-slate-500">ESTADO DA TRANSMISSÃO</span>
            <Badge tone={running ? "live" : "off"}>{running ? "Em direto" : "Parado"}</Badge>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {metrics.map((m, i) => {
              const Icon = m.icon;
              return (
                <div key={i} className="rounded-xl bg-slate-800/40 border border-slate-800 p-3">
                  <Icon className="h-4 w-4 mb-1" style={{ color: m.color }} />
                  <div className="text-[10px] font-bold text-slate-500">{m.label}</div>
                  <div className="text-sm font-bold text-white truncate">{m.value}</div>
                  <div className="text-[10px] text-slate-500">{m.sub}</div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Controlos */}
        <Card className="p-5">
          <div className="text-xs font-bold tracking-wide text-slate-500 mb-4">CONTROLOS</div>
          <div className="space-y-2">
            <Toggle label="Mostrar logotipo" checked={!!court.logo_path} disabled />
            <Toggle label="Mostrar texto" checked={!!court.overlay_text} onChange={(v) => patchToggle("overlay_text" as any, v ? court.overlay_text || " " : "" as any)} />
            <Toggle label="Mostrar hora" checked={court.show_clock} onChange={(v) => patchToggle("show_clock", v)} />
          </div>
          <div className="mt-4 space-y-2">
            <Button variant="outline" className="w-full" onClick={restart} disabled={busy}><RotateCw className="h-4 w-4" /> Reiniciar ligação</Button>
            <Button variant="danger" className="w-full" onClick={stop} disabled={busy}><Square className="h-4 w-4" /> Terminar transmissão</Button>
          </div>
        </Card>
      </div>
    </div>
  );
}

const Toggle: React.FC<{ label: string; checked: boolean; disabled?: boolean; onChange?: (v: boolean) => void }> = ({ label, checked, disabled, onChange }) => (
  <label className={`flex items-center justify-between px-3 py-2.5 rounded-xl bg-slate-800/40 border border-slate-800 ${disabled ? "opacity-60" : "cursor-pointer"}`}>
    <span className="text-sm text-slate-300">{label}</span>
    <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange?.(e.target.checked)} className="accent-teal-400" />
  </label>
);

function uptime(started?: string | null): string {
  if (!started) return "—";
  const ms = Date.now() - new Date(started).getTime();
  if (ms < 0 || isNaN(ms)) return "—";
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
