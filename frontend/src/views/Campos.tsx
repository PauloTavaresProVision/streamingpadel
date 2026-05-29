import React, { useEffect, useState } from "react";
import { Plus, Save, Trash2, Camera, Search, Link2, Eye, Settings2, Wifi, Copy, ListOrdered, RefreshCw, CheckCircle2 } from "lucide-react";
import { api, Court } from "../api";
import { Button, Card, Brand } from "../ui";

export default function Campos() {
  const [courts, setCourts] = useState<Court[]>([]);
  const [online, setOnline] = useState<Record<string, boolean>>({});
  const [sel, setSel] = useState<Court | null>(null);
  const [tab, setTab] = useState<"ligacao" | "preview" | "avancado">("ligacao");
  const [q, setQ] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<null | boolean>(null);
  const [toast, setToast] = useState("");
  const t = (m: string) => { setToast(m); setTimeout(() => setToast(""), 2500); };

  const load = async () => {
    const cs = await api.listCourts(); setCourts(cs);
    setSel((s) => (s ? cs.find((c) => c.id === s.id) || cs[0] : cs[0]) || null);
  };
  const loadOnline = async () => { try { setOnline(await api.camerasOnline()); } catch {} };
  useEffect(() => { load(); loadOnline(); const i = setInterval(loadOnline, 12000); return () => clearInterval(i); }, []);

  const patch = (k: keyof Court, v: any) => setSel((c) => (c ? { ...c, [k]: v } : c));
  const save = async () => { if (!sel) return; try { await api.updateCourt(sel.id, sel); await load(); t("Alterações guardadas"); } catch (e: any) { t("Erro: " + e.message); } };
  const create = async () => { const name = prompt("Nome do novo campo:"); if (!name) return; const c = await api.createCourt(name); await load(); setSel(c); };
  const remove = async () => { if (!sel || !confirm(`Eliminar "${sel.name}"?`)) return; await api.deleteCourt(sel.id); setSel(null); await load(); };
  const test = async () => { if (!sel) return; setTesting(true); setTestResult(null); try { const o = await api.camerasOnline(); setTestResult(!!o[sel.id]); setOnline(o); } finally { setTesting(false); } };

  const filtered = courts.filter((c) => c.name.toLowerCase().includes(q.toLowerCase()));
  const rtspFinal = sel ? `rtsp://${sel.nvr_user}:••••••••@${sel.camera_ip}${sel.rtsp_path || "/Streaming/Channels/101"}` : "";

  return (
    <div className="p-8 max-w-[1500px] mx-auto">
      <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
        <div><h1 className="text-3xl font-extrabold text-white">Câmaras</h1><p className="text-slate-400 text-sm mt-1">Gestão e configuração das câmaras de cada campo</p></div>
        <div className="flex items-center gap-3">
          <div className="relative"><Search className="h-4 w-4 absolute left-3 top-3 text-slate-500" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Pesquisar campos..." className="inp pl-9 w-64" /></div>
          <Button variant="primary" onClick={create}><Plus className="h-4 w-4" /> Novo campo</Button>
        </div>
      </div>

      <div className="grid lg:grid-cols-[340px_1fr] gap-6 items-start">
        {/* Lista */}
        <Card className="p-4">
          <div className="text-xs font-bold tracking-wide text-slate-500 mb-3 flex items-center justify-between">CAMPOS CONFIGURADOS <span className="text-teal-400">{courts.length}</span></div>
          <div className="space-y-2">
            {filtered.map((c) => {
              const on = online[c.id];
              return (
                <button key={c.id} onClick={() => { setSel(c); setTestResult(null); }}
                  className={`w-full text-left px-3 py-3 rounded-xl border flex items-center gap-3 transition ${sel?.id === c.id ? "bg-teal-500/10 border-teal-500/50" : "bg-slate-800/30 border-slate-800 hover:border-slate-700"}`}>
                  <span className="w-9 h-9 rounded-lg bg-slate-800 flex items-center justify-center"><Camera className="h-4 w-4 text-slate-400" /></span>
                  <div className="flex-1 min-w-0"><div className="font-semibold text-sm text-white truncate">{c.name}</div><div className="text-xs text-slate-500">{c.camera_ip}</div></div>
                  <span className={`text-[11px] font-semibold flex items-center gap-1 ${on ? "text-emerald-400" : "text-amber-400"}`}><span className={`w-1.5 h-1.5 rounded-full ${on ? "bg-emerald-400" : "bg-amber-400"}`} /> {on ? "Online" : "Offline"}</span>
                </button>
              );
            })}
          </div>
          <button className="w-full mt-3 py-2.5 rounded-xl border border-slate-800 text-slate-400 text-sm flex items-center justify-center gap-2 hover:border-slate-700"><ListOrdered className="h-4 w-4" /> Gerir ordem</button>
        </Card>

        {/* Detalhe */}
        {sel && (
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3"><h2 className="text-lg font-bold text-white">Detalhes da câmara</h2><span className={`text-xs font-semibold flex items-center gap-1.5 ${online[sel.id] ? "text-emerald-400" : "text-amber-400"}`}><span className={`w-2 h-2 rounded-full ${online[sel.id] ? "bg-emerald-400" : "bg-amber-400"}`} /> {online[sel.id] ? "Online" : "Offline"}</span></div>
              <div className="text-xs text-slate-500 flex items-center gap-1"><RefreshCw className="h-3.5 w-3.5" /> Verificado periodicamente</div>
            </div>

            <div className="flex gap-6 border-b border-slate-800 mb-5">
              {([["ligacao", "Ligação", Link2], ["preview", "Preview", Eye], ["avancado", "Avançado", Settings2]] as const).map(([id, label, Icon]) => (
                <button key={id} onClick={() => setTab(id)} className={`flex items-center gap-2 pb-3 text-sm font-semibold ${tab === id ? "text-teal-400 border-b-2 border-teal-400" : "text-slate-500"}`}><Icon className="h-4 w-4" /> {label}</button>
              ))}
            </div>

            {tab === "preview" ? (
              <div>
                <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden">
                  <img src={api.snapshotUrl(sel.id)} alt="" className="w-full h-full object-contain" onError={(e) => ((e.currentTarget as HTMLImageElement).style.opacity = "0")} />
                </div>
                <Button variant="outline" size="sm" className="mt-3" onClick={() => { const img = new Image(); img.src = api.snapshotUrlFresh(sel.id); img.onload = () => load(); }}><RefreshCw className="h-4 w-4" /> Actualizar imagem</Button>
              </div>
            ) : tab === "avancado" ? (
              <div className="grid sm:grid-cols-3 gap-4">
                <F t="Resolução"><select className="inp" value={sel.resolution} onChange={(e) => patch("resolution", e.target.value)}><option className="bg-slate-900">720p</option><option className="bg-slate-900">1080p</option></select></F>
                <F t="Bitrate (kbps)"><input type="number" className="inp" value={sel.bitrate_kbps} onChange={(e) => patch("bitrate_kbps", +e.target.value)} /></F>
                <F t="FPS"><input type="number" className="inp" value={sel.fps} onChange={(e) => patch("fps", +e.target.value)} /></F>
              </div>
            ) : (
              <div className="grid lg:grid-cols-[300px_1fr] gap-6">
                {/* Preview ao vivo + estado */}
                <div>
                  <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden">
                    <span className="absolute top-2 left-2 text-[10px] font-bold text-white/80 z-10">Preview ao vivo</span>
                    {online[sel.id] && <span className="absolute top-2 right-2 text-[10px] font-bold text-red-400 z-10 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-red-500" /> LIVE</span>}
                    <img src={api.snapshotUrl(sel.id)} alt="" className="w-full h-full object-cover" onError={(e) => ((e.currentTarget as HTMLImageElement).style.opacity = "0")} />
                    <div className="absolute bottom-2 left-1/2 -translate-x-1/2 opacity-80"><Brand compact /></div>
                  </div>
                  <div className="mt-3 p-3 rounded-xl bg-slate-800/40 border border-slate-800">
                    <div className="text-[11px] font-bold text-slate-500 mb-1">ESTADO DA LIGAÇÃO</div>
                    <div className="flex items-center gap-2"><Wifi className={`h-4 w-4 ${online[sel.id] ? "text-emerald-400" : "text-amber-400"}`} />
                      <div><div className="text-sm font-semibold text-white">{online[sel.id] ? "Ligação estável" : "Sem ligação"}</div><div className="text-[11px] text-slate-500">{sel.resolution} • {sel.fps} fps</div></div>
                    </div>
                  </div>
                </div>

                {/* Campos */}
                <div className="space-y-4">
                  <F t="Nome do campo"><input className="inp" value={sel.name} onChange={(e) => patch("name", e.target.value)} /></F>
                  <div className="grid grid-cols-2 gap-4">
                    <F t="IP da câmara"><input className="inp" value={sel.camera_ip} onChange={(e) => patch("camera_ip", e.target.value)} /></F>
                    <F t="Caminho RTSP"><input className="inp" value={sel.rtsp_path ?? ""} placeholder="/Streaming/Channels/101" onChange={(e) => patch("rtsp_path", e.target.value)} /></F>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <F t="Utilizador"><input className="inp" value={sel.nvr_user} onChange={(e) => patch("nvr_user", e.target.value)} /></F>
                    <F t="Password"><div className="relative"><input type={showPwd ? "text" : "password"} className="inp pr-10" value={sel.nvr_password} onChange={(e) => patch("nvr_password", e.target.value)} /><button onClick={() => setShowPwd(!showPwd)} className="absolute right-3 top-3 text-slate-500"><Eye className="h-4 w-4" /></button></div></F>
                  </div>
                  <F t="URL RTSP final">
                    <div className="flex gap-2"><input readOnly className="inp font-mono text-xs text-slate-400" value={rtspFinal} /><Button variant="outline" size="sm" onClick={() => { navigator.clipboard.writeText(rtspFinal.replace("••••••••", sel.nvr_password)); t("URL copiada"); }}><Copy className="h-4 w-4" /></Button></div>
                  </F>
                  <p className="text-xs text-slate-500">Esta é a URL completa utilizada para a transmissão de vídeo.</p>
                  <div className="flex items-center gap-3">
                    <Button variant="primary" onClick={test} disabled={testing}><Wifi className="h-4 w-4" /> {testing ? "A testar..." : "Testar ligação"}</Button>
                    {testResult === true && <span className="text-sm text-emerald-400 flex items-center gap-1"><CheckCircle2 className="h-4 w-4" /> Ligação bem-sucedida</span>}
                    {testResult === false && <span className="text-sm text-red-400">Sem resposta</span>}
                  </div>
                </div>
              </div>
            )}

            <div className="flex items-center gap-3 mt-6 pt-5 border-t border-slate-800">
              <Button variant="teal" onClick={save}><Save className="h-4 w-4" /> Guardar alterações</Button>
              <Button variant="outline" onClick={test}><Wifi className="h-4 w-4" /> Testar ligação</Button>
              <Button variant="outline" className="ml-auto text-red-400 border-red-500/40 hover:bg-red-500/10" onClick={remove}><Trash2 className="h-4 w-4" /> Eliminar campo</Button>
            </div>
          </Card>
        )}
      </div>
      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-800 border border-slate-700 text-white px-5 py-3 rounded-xl text-sm">{toast}</div>}
    </div>
  );
}
const F: React.FC<{ t: string; children: React.ReactNode }> = ({ t, children }) => (
  <div><label className="block text-xs font-semibold text-slate-400 mb-1.5">{t}</label>{children}</div>
);
