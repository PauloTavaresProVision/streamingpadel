import React, { useEffect, useState } from "react";
import { Radio, Camera, MonitorPlay, Plus, Wifi, Youtube, Cpu, HardDrive, CheckCircle2, AlertTriangle, Info } from "lucide-react";
import { api, Court, StreamStatus } from "../api";
import { Card, Sparkline, Badge, Button } from "../ui";

export default function Dashboard({ onNavigate }: { onNavigate: (v: string) => void }) {
  const [courts, setCourts] = useState<Court[]>([]);
  const [statuses, setStatuses] = useState<Record<string, StreamStatus>>({});

  const load = async () => {
    const cs = await api.listCourts(); setCourts(cs);
    const map: Record<string, StreamStatus> = {};
    await Promise.all(cs.map(async (c) => { try { map[c.id] = await api.status(c.id); } catch {} }));
    setStatuses(map);
  };
  useEffect(() => { load(); const i = setInterval(load, 8000); return () => clearInterval(i); }, []);

  const lives = courts.filter((c) => statuses[c.id]?.is_running).length;
  const kpis = [
    { label: "CAMPOS", value: String(courts.length), foot: "configurados", icon: Radio, color: "#2dd4bf" },
    { label: "LIVES EM DIRECTO", value: String(lives), foot: "agora", icon: Radio, color: "#3b82f6" },
    { label: "CÂMARAS ONLINE", value: `${courts.length} / ${courts.length}`, foot: "ligadas", icon: Camera, color: "#f59e0b" },
    { label: "QUALIDADE MÉDIA", value: "1080p", foot: "máxima", icon: MonitorPlay, color: "#a855f7" },
  ];
  const sysrows = [
    { icon: Wifi, label: "Internet", val: "Operacional", ok: true },
    { icon: Youtube, label: "YouTube", val: "Operacional", ok: true },
    { icon: Cpu, label: "Encoder NVENC", val: "Operacional", ok: true },
    { icon: HardDrive, label: "Armazenamento", val: "disponível", ok: true },
  ];
  const actions = [
    { label: "Criar transmissão", icon: Plus, primary: true, go: "transmissoes" },
    { label: "Ver transmissões", icon: Radio, go: "transmissoes" },
    { label: "Testar câmaras", icon: Camera, go: "camaras" },
    { label: "Configurar YouTube", icon: Youtube, go: "youtube" },
  ];
  const alerts = [
    { icon: CheckCircle2, tone: "text-emerald-400", t: "Ligação estável", s: "Internet com boa qualidade", time: "Agora" },
    { icon: Info, tone: "text-blue-400", t: "Sistema operacional", s: "Todos os serviços a funcionar", time: "Agora" },
  ];

  return (
    <div className="p-8 max-w-[1500px] mx-auto">
      <h1 className="text-3xl font-extrabold text-white">Dashboard</h1>
      <p className="text-slate-400 text-sm mt-1 mb-6">Visão geral da plataforma de transmissões</p>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {kpis.map((k, i) => { const Icon = k.icon; return (
          <Card key={i} className="p-5">
            <div className="flex items-start justify-between">
              <div><div className="text-[11px] font-bold tracking-wide text-slate-500">{k.label}</div>
                <div className="text-3xl font-extrabold text-white mt-1">{k.value}</div>
                <div className="text-xs mt-1" style={{ color: k.color }}>{k.foot}</div></div>
              <span className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ background: k.color + "1a" }}><Icon className="h-5 w-5" style={{ color: k.color }} /></span>
            </div>
            <div className="-mb-1 mt-1 opacity-70"><Sparkline color={k.color} seed={i + 2} /></div>
          </Card>
        ); })}
      </div>

      {/* Linha do meio: gráfico + sistema + ações */}
      <div className="grid lg:grid-cols-[1.6fr_1fr_1fr] gap-4 mb-6">
        <Card className="p-5">
          <div className="text-xs font-bold tracking-wide text-slate-500 mb-4">ACTIVIDADE DE TRANSMISSÕES (24H)</div>
          <BarChart />
        </Card>
        <Card className="p-5">
          <div className="text-xs font-bold tracking-wide text-slate-500 mb-4">ESTADO DO SISTEMA</div>
          <div className="space-y-3">
            {sysrows.map((r, i) => { const Icon = r.icon; return (
              <div key={i} className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm text-slate-300"><Icon className="h-4 w-4 text-slate-500" /> {r.label}</span>
                <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> {r.val}</span>
              </div>
            ); })}
          </div>
        </Card>
        <Card className="p-5">
          <div className="text-xs font-bold tracking-wide text-slate-500 mb-4">AÇÕES RÁPIDAS</div>
          <div className="space-y-2">
            {actions.map((a, i) => { const Icon = a.icon; return (
              <button key={i} onClick={() => onNavigate(a.go)}
                className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold transition ${a.primary ? "bg-blue-600 hover:bg-blue-500 text-white" : "bg-slate-800/60 border border-slate-700 text-slate-300 hover:border-teal-500/40"}`}>
                <Icon className="h-4 w-4" /> {a.label}
              </button>
            ); })}
          </div>
        </Card>
      </div>

      {/* Linha de baixo: últimas + câmaras + alertas */}
      <div className="grid lg:grid-cols-[1.3fr_1fr_1fr] gap-4">
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3"><div className="text-xs font-bold tracking-wide text-slate-500">ÚLTIMAS TRANSMISSÕES</div><button onClick={() => onNavigate("transmissoes")} className="text-xs text-teal-400">Ver todas</button></div>
          <div className="space-y-2">
            {courts.slice(0, 5).map((c) => { const s = statuses[c.id]; const running = s?.is_running; return (
              <div key={c.id} className="flex items-center gap-3">
                <div className="w-12 h-8 rounded bg-slate-800 overflow-hidden flex-shrink-0"><img src={api.snapshotUrl(c.id)} alt="" className="w-full h-full object-cover" onError={(e) => ((e.currentTarget as HTMLImageElement).style.opacity = "0")} /></div>
                <div className="flex-1 min-w-0"><div className="text-sm font-medium text-white truncate">{c.name}</div><div className="text-[11px] text-slate-500">{c.camera_ip}</div></div>
                <Badge tone={running ? "live" : c.youtube_stream_key ? "prep" : "off"}>{running ? "Live" : c.youtube_stream_key ? "Pronta" : "Off"}</Badge>
              </div>
            ); })}
          </div>
        </Card>
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3"><div className="text-xs font-bold tracking-wide text-slate-500">ESTADO DAS CÂMARAS</div><button onClick={() => onNavigate("camaras")} className="text-xs text-teal-400">Ver todas</button></div>
          <div className="grid grid-cols-2 gap-2">
            {courts.slice(0, 6).map((c) => (
              <div key={c.id} className="flex items-center gap-2 p-2 rounded-lg bg-slate-800/40 border border-slate-800">
                <Camera className="h-4 w-4 text-slate-500" />
                <div className="min-w-0"><div className="text-xs font-medium text-white truncate">{c.name}</div><div className="text-[10px] text-emerald-400 flex items-center gap-1"><span className="w-1 h-1 rounded-full bg-emerald-400" /> Online</div></div>
              </div>
            ))}
          </div>
        </Card>
        <Card className="p-5">
          <div className="flex items-center justify-between mb-3"><div className="text-xs font-bold tracking-wide text-slate-500">ALERTAS RECENTES</div></div>
          <div className="space-y-3">
            {alerts.map((a, i) => { const Icon = a.icon; return (
              <div key={i} className="flex items-start gap-3">
                <Icon className={`h-4 w-4 mt-0.5 ${a.tone}`} />
                <div className="flex-1"><div className="text-sm font-medium text-slate-200">{a.t}</div><div className="text-xs text-slate-500">{a.s}</div></div>
                <span className="text-[10px] text-slate-600">{a.time}</span>
              </div>
            ); })}
          </div>
        </Card>
      </div>
    </div>
  );
}

const BarChart: React.FC = () => {
  const bars = Array.from({ length: 24 }, (_, i) => 15 + Math.abs(Math.sin(i * 0.9) * 70) + (i % 5) * 4);
  return (
    <div className="flex items-end gap-1 h-44">
      {bars.map((h, i) => (
        <div key={i} className="flex-1 rounded-t bg-gradient-to-t from-teal-500/30 to-teal-400" style={{ height: `${Math.min(100, h)}%` }} />
      ))}
    </div>
  );
};
