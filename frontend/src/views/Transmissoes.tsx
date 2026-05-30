import React, { useEffect, useState } from "react";
import { Search, Plus, Radio, Calendar, Pause, MonitorPlay, Camera, Youtube, MoreVertical, ExternalLink, Link2, Play, Square } from "lucide-react";
import { api, Court, StreamStatus } from "../api";
import { Button, Card, Badge, Sparkline } from "../ui";
import Editor from "./Editor";
import Live from "./Live";
import Wizard from "./Wizard";

type Sub = { kind: "list" } | { kind: "editor"; court: Court } | { kind: "live"; court: Court } | { kind: "wizard" };

export default function Transmissoes() {
  const [sub, setSub] = useState<Sub>({ kind: "list" });
  const [courts, setCourts] = useState<Court[]>([]);
  const [statuses, setStatuses] = useState<Record<string, StreamStatus>>({});
  const [online, setOnline] = useState<Record<string, boolean>>({});
  const [q, setQ] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);

  const loadAll = async () => {
    const cs = await api.listCourts();
    setCourts(cs);
    const map: Record<string, StreamStatus> = {};
    await Promise.all(cs.map(async (c) => { try { map[c.id] = await api.status(c.id); } catch {} }));
    setStatuses(map);
  };
  const loadOnline = async () => { try { setOnline(await api.camerasOnline()); } catch {} };
  const startAll = async () => {
    if (!confirm("Iniciar a transmissão de TODOS os campos com stream key?")) return;
    setBulkBusy(true);
    try { const r = await api.startAll(); alert(`${r.started} campo(s) a iniciar.`); } catch (e: any) { alert("Erro: " + e.message); }
    finally { setBulkBusy(false); loadAll(); }
  };
  const stopAll = async () => {
    if (!confirm("Parar a transmissão de TODOS os campos?")) return;
    setBulkBusy(true);
    try { await api.stopAll(); } catch (e: any) { alert("Erro: " + e.message); }
    finally { setBulkBusy(false); loadAll(); }
  };
  useEffect(() => {
    loadAll(); loadOnline();
    const i = setInterval(loadAll, 8000);
    const j = setInterval(loadOnline, 10000);  // ping câmaras de 10 em 10s
    return () => { clearInterval(i); clearInterval(j); };
  }, []);

  if (sub.kind === "editor") return <Editor court={sub.court} onBack={() => { setSub({ kind: "list" }); loadAll(); }} />;
  if (sub.kind === "live") return <Live court={sub.court} onBack={() => { setSub({ kind: "list" }); loadAll(); }} />;
  if (sub.kind === "wizard") return <Wizard onDone={(c) => { setSub(c ? { kind: "editor", court: c } : { kind: "list" }); loadAll(); }} />;

  const live = courts.filter((c) => statuses[c.id]?.is_running).length;
  const configured = courts.filter((c) => c.youtube_stream_key).length;
  const filtered = courts.filter((c) => c.name.toLowerCase().includes(q.toLowerCase()));

  const kpis = [
    { label: "TRANSMISSÕES ATIVAS", value: String(live), foot: "Em direto agora", icon: Radio, color: "#2dd4bf" },
    { label: "TOTAL CAMPOS", value: String(courts.length), foot: "configurados", icon: Calendar, color: "#3b82f6" },
    { label: "PRONTAS", value: String(configured), foot: "com stream key", icon: Pause, color: "#f59e0b" },
    { label: "QUALIDADE", value: "1080p", foot: "máxima", icon: MonitorPlay, color: "#a855f7" },
  ];

  return (
    <div className="p-8 max-w-[1500px] mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
        <div>
          <h1 className="text-3xl font-extrabold text-white">Transmissões</h1>
          <p className="text-slate-400 text-sm mt-1">Gerir e monitorizar todas as transmissões em direto</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="h-4 w-4 absolute left-3 top-3 text-slate-500" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Pesquisar transmissões..." className="inp pl-9 w-72" />
          </div>
          <Button variant="teal" disabled={bulkBusy} onClick={startAll}><Play className="h-4 w-4" /> Iniciar todos</Button>
          <Button variant="danger" disabled={bulkBusy} onClick={stopAll}><Square className="h-4 w-4" /> Parar todos</Button>
          <Button variant="primary" onClick={() => setSub({ kind: "wizard" })}><Plus className="h-4 w-4" /> Criar nova transmissão</Button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {kpis.map((k, i) => {
          const Icon = k.icon;
          return (
            <Card key={i} className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-[11px] font-bold tracking-wide text-slate-500">{k.label}</div>
                  <div className="text-3xl font-extrabold text-white mt-1">{k.value}</div>
                  <div className="text-xs mt-1" style={{ color: k.color }}>{k.foot}</div>
                </div>
                <span className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ background: k.color + "1a" }}>
                  <Icon className="h-5 w-5" style={{ color: k.color }} />
                </span>
              </div>
              <div className="-mb-1 mt-1 opacity-70"><Sparkline color={k.color} seed={i + 1} /></div>
            </Card>
          );
        })}
      </div>

      {/* Tabela */}
      <Card className="overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] font-bold tracking-wide text-slate-500 border-b border-slate-800">
              <th className="text-left px-5 py-3.5">NOME DA TRANSMISSÃO</th>
              <th className="text-left px-3 py-3.5">ESTADO</th>
              <th className="text-left px-3 py-3.5">CÂMARA</th>
              <th className="text-left px-3 py-3.5">QUALIDADE</th>
              <th className="text-left px-3 py-3.5">TEMPO LIVE</th>
              <th className="text-left px-3 py-3.5">YOUTUBE</th>
              <th className="text-right px-5 py-3.5">AÇÕES</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => {
              const s = statuses[c.id];
              const running = s?.is_running;
              const isOnline = online[c.id];
              const tone = running ? "live" : s?.last_error ? "err" : isOnline ? "prep" : "off";
              const estado = running ? "Live" : s?.last_error ? "Com erro" : isOnline ? "Online" : "Offline";
              return (
                <tr key={c.id} className="border-b border-slate-800/60 hover:bg-slate-800/30 transition">
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-3">
                      <div className="w-16 h-10 rounded-lg bg-slate-800 overflow-hidden flex-shrink-0">
                        <img src={api.snapshotUrl(c.id)} alt="" className="w-full h-full object-cover" onError={(e) => ((e.currentTarget as HTMLImageElement).style.opacity = "0")} />
                      </div>
                      <div>
                        <div className="font-semibold text-white">{c.name}</div>
                        <div className="text-xs text-slate-500">{c.camera_ip}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3"><Badge tone={tone as any}>{estado}</Badge></td>
                  <td className="px-3"><div className="flex items-center gap-2 text-slate-300"><Camera className="h-4 w-4 text-slate-500" /> {c.name}</div></td>
                  <td className="px-3"><div className="text-slate-200 font-medium">{c.resolution}</div><div className="text-xs text-teal-400">{c.fps} fps</div></td>
                  <td className="px-3">{running ? <span className="text-emerald-400 font-mono">{uptime(s?.started_at)}</span> : <span className="text-slate-500">—</span>}</td>
                  <td className="px-3">
                    {c.youtube_watch_url
                      ? <a href={c.youtube_watch_url} target="_blank" className="inline-flex items-center gap-1.5 text-red-400 hover:text-red-300"><Youtube className="h-4 w-4" /> Ver live <ExternalLink className="h-3 w-3" /></a>
                      : <button onClick={() => setSub({ kind: "editor", court: c })} className="inline-flex items-center gap-1.5 text-blue-400 hover:text-blue-300"><Link2 className="h-4 w-4" /> Definir</button>}
                  </td>
                  <td className="px-5 text-right">
                    <div className="inline-flex items-center gap-1">
                      {running && <Button variant="ghost" size="sm" onClick={() => setSub({ kind: "live", court: c })}>Monitor</Button>}
                      <Button variant="outline" size="sm" onClick={() => setSub({ kind: "editor", court: c })}>Editar</Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && <div className="text-center text-slate-500 py-10 text-sm">Sem transmissões.</div>}
      </Card>
    </div>
  );
}

function uptime(started?: string | null): string {
  if (!started) return "—";
  const ms = Date.now() - new Date(started).getTime();
  if (ms < 0 || isNaN(ms)) return "—";
  const s = Math.floor(ms / 1000);
  const h = String(Math.floor(s / 3600)).padStart(2, "0");
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${h}:${m}:${ss}`;
}
