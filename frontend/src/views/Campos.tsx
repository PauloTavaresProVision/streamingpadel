import React, { useEffect, useState } from "react";
import { Plus, Save, Trash2, Camera, Search, Eye, Wifi, Copy, RefreshCw, CheckCircle2, X, Pencil } from "lucide-react";
import { api, Court } from "../api";
import { Button, Card } from "../ui";

export default function Campos() {
  const [courts, setCourts] = useState<Court[]>([]);
  const [online, setOnline] = useState<Record<string, boolean>>({});
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<Court | null>(null);
  const [toast, setToast] = useState("");
  const t = (m: string) => { setToast(m); setTimeout(() => setToast(""), 2500); };

  const load = async () => setCourts(await api.listCourts());
  const loadOnline = async () => { try { setOnline(await api.camerasOnline()); } catch {} };
  useEffect(() => { load(); loadOnline(); const i = setInterval(loadOnline, 12000); return () => clearInterval(i); }, []);

  const create = async () => { const c = await api.createCourt(`Campo ${courts.length + 1}`); await load(); setEditing(c); };
  const filtered = courts.filter((c) => c.name.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="p-8 max-w-[1200px] mx-auto">
      <div className="flex items-start justify-between gap-4 mb-6 flex-wrap">
        <div><h1 className="text-3xl font-extrabold text-white">Câmaras</h1><p className="text-slate-400 text-sm mt-1">Gestão e configuração das câmaras de cada campo</p></div>
        <div className="flex items-center gap-3">
          <div className="relative"><Search className="h-4 w-4 absolute left-3 top-3 text-slate-500" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Pesquisar campos..." className="inp pl-9 w-64" /></div>
          <Button variant="primary" onClick={create}><Plus className="h-4 w-4" /> Novo campo</Button>
        </div>
      </div>

      <Card className="overflow-hidden">
        <div className="px-5 py-3 text-xs font-bold tracking-wide text-slate-500 border-b border-slate-800 flex items-center justify-between">
          CAMPOS CONFIGURADOS <span className="text-teal-400">{courts.length}</span>
        </div>
        <table className="w-full text-sm">
          <thead><tr className="text-[11px] font-bold tracking-wide text-slate-500 border-b border-slate-800">
            <th className="text-left px-5 py-3">CAMPO</th><th className="text-left px-3 py-3">IP</th>
            <th className="text-left px-3 py-3">RTSP</th><th className="text-left px-3 py-3">QUALIDADE</th>
            <th className="text-left px-3 py-3">ESTADO</th><th className="text-right px-5 py-3">AÇÕES</th>
          </tr></thead>
          <tbody>
            {filtered.map((c) => {
              const on = online[c.id];
              return (
                <tr key={c.id} className="border-b border-slate-800/60 hover:bg-slate-800/30">
                  <td className="px-5 py-3.5"><div className="flex items-center gap-3"><span className="w-9 h-9 rounded-lg bg-slate-800 flex items-center justify-center"><Camera className="h-4 w-4 text-slate-400" /></span><span className="font-semibold text-white">{c.name}</span></div></td>
                  <td className="px-3 text-slate-300 font-mono text-xs">{c.camera_ip || "—"}</td>
                  <td className="px-3 text-slate-500 font-mono text-xs truncate max-w-[200px]">{c.rtsp_path || "/Streaming/Channels/101"}</td>
                  <td className="px-3 text-slate-300">{c.resolution} · {c.fps}fps</td>
                  <td className="px-3"><span className={`inline-flex items-center gap-1.5 text-xs font-semibold ${on ? "text-emerald-400" : "text-amber-400"}`}><span className={`w-1.5 h-1.5 rounded-full ${on ? "bg-emerald-400" : "bg-amber-400"}`} /> {on ? "Online" : "Offline"}</span></td>
                  <td className="px-5 text-right"><Button variant="outline" size="sm" onClick={() => setEditing(c)}><Pencil className="h-4 w-4" /> Editar</Button></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && <div className="text-center text-slate-500 py-10 text-sm">Sem campos.</div>}
      </Card>

      {editing && <CameraEditor court={editing} online={!!online[editing.id]} onClose={() => setEditing(null)} onSaved={async () => { await load(); await loadOnline(); }} toast={t} />}
      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-800 border border-slate-700 text-white px-5 py-3 rounded-xl text-sm z-50">{toast}</div>}
    </div>
  );
}

function CameraEditor({ court: initial, online, onClose, onSaved, toast }: { court: Court; online: boolean; onClose: () => void; onSaved: () => Promise<void>; toast: (m: string) => void }) {
  const [c, setC] = useState<Court>(initial);
  const [showPwd, setShowPwd] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testRes, setTestRes] = useState<null | boolean>(null);
  const patch = (k: keyof Court, v: any) => setC((p) => ({ ...p, [k]: v }));

  const save = async () => { try { await api.updateCourt(c.id, c); await onSaved(); toast("Alterações guardadas"); onClose(); } catch (e: any) { toast("Erro: " + e.message); } };
  const remove = async () => { if (!confirm(`Eliminar "${c.name}"?`)) return; await api.deleteCourt(c.id); await onSaved(); onClose(); };
  const test = async () => { setTesting(true); setTestRes(null); try { const o = await api.camerasOnline(); setTestRes(!!o[c.id]); } finally { setTesting(false); } };

  const rtspFinal = `rtsp://${c.nvr_user}:${"•".repeat(8)}@${c.camera_ip}${c.rtsp_path || "/Streaming/Channels/101"}`;

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 overflow-auto" onClick={onClose}>
      <div className="bg-[#0c1220] border border-slate-800 rounded-2xl w-full max-w-4xl my-8" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800">
          <div className="flex items-center gap-3"><h2 className="text-lg font-bold text-white">{initial.name}</h2><span className={`text-xs font-semibold flex items-center gap-1.5 ${online ? "text-emerald-400" : "text-amber-400"}`}><span className={`w-2 h-2 rounded-full ${online ? "bg-emerald-400" : "bg-amber-400"}`} /> {online ? "Online" : "Offline"}</span></div>
          <button onClick={onClose} className="text-slate-500 hover:text-white"><X className="h-5 w-5" /></button>
        </div>

        <div className="grid md:grid-cols-[360px_1fr] gap-6 p-6">
          <div>
            <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden">
              <span className="absolute top-2 left-2 text-[10px] font-bold text-white/80 z-10">Preview ao vivo</span>
              <img src={api.snapshotUrl(c.id)} alt="" className="w-full h-full object-cover" onError={(e) => ((e.currentTarget as HTMLImageElement).style.opacity = "0")} />
            </div>
            <div className="mt-3 p-3 rounded-xl bg-slate-800/40 border border-slate-800">
              <div className="text-[11px] font-bold text-slate-500 mb-1">ESTADO DA LIGAÇÃO</div>
              <div className="flex items-center gap-2"><Wifi className={`h-4 w-4 ${online ? "text-emerald-400" : "text-amber-400"}`} /><div><div className="text-sm font-semibold text-white">{online ? "Ligação estável" : "Sem ligação"}</div><div className="text-[11px] text-slate-500">{c.resolution} • {c.fps} fps</div></div></div>
            </div>
            <Button variant="outline" size="sm" className="mt-3 w-full" onClick={() => { const img = new Image(); img.src = api.snapshotUrlFresh(c.id); }}><RefreshCw className="h-4 w-4" /> Actualizar imagem</Button>
          </div>

          <div className="space-y-4">
            <F t="Nome do campo"><input className="inp" value={c.name} onChange={(e) => patch("name", e.target.value)} /></F>
            <F t="IP da câmara"><input className="inp" value={c.camera_ip} onChange={(e) => patch("camera_ip", e.target.value)} /></F>
            <F t="Caminho RTSP"><input className="inp" value={c.rtsp_path ?? ""} placeholder="/Streaming/Channels/101" onChange={(e) => patch("rtsp_path", e.target.value)} /></F>
            <div className="grid grid-cols-2 gap-4">
              <F t="Utilizador"><input className="inp" value={c.nvr_user} onChange={(e) => patch("nvr_user", e.target.value)} /></F>
              <F t="Password"><div className="relative"><input type={showPwd ? "text" : "password"} className="inp pr-10" value={c.nvr_password} onChange={(e) => patch("nvr_password", e.target.value)} /><button onClick={() => setShowPwd(!showPwd)} className="absolute right-3 top-3 text-slate-500"><Eye className="h-4 w-4" /></button></div></F>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <F t="Resolução"><select className="inp" value={c.resolution} onChange={(e) => patch("resolution", e.target.value)}><option className="bg-slate-900">720p</option><option className="bg-slate-900">1080p</option></select></F>
              <F t="Bitrate (kbps)"><input type="number" className="inp" value={c.bitrate_kbps} onChange={(e) => patch("bitrate_kbps", +e.target.value)} /></F>
              <F t="FPS"><input type="number" className="inp" value={c.fps} onChange={(e) => patch("fps", +e.target.value)} /></F>
            </div>
            <F t="URL RTSP final"><div className="flex gap-2"><input readOnly className="inp font-mono text-xs text-slate-400" value={rtspFinal} /><Button variant="outline" size="sm" onClick={() => { navigator.clipboard.writeText(rtspFinal.replace("••••••••", c.nvr_password)); toast("URL copiada"); }}><Copy className="h-4 w-4" /></Button></div></F>
            <div className="flex items-center gap-3">
              <Button variant="primary" onClick={test} disabled={testing}><Wifi className="h-4 w-4" /> {testing ? "A testar..." : "Testar ligação"}</Button>
              {testRes === true && <span className="text-sm text-emerald-400 flex items-center gap-1"><CheckCircle2 className="h-4 w-4" /> Ligação bem-sucedida</span>}
              {testRes === false && <span className="text-sm text-red-400">Sem resposta</span>}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 px-6 py-4 border-t border-slate-800">
          <Button variant="teal" onClick={save}><Save className="h-4 w-4" /> Guardar alterações</Button>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button variant="outline" className="ml-auto text-red-400 border-red-500/40 hover:bg-red-500/10" onClick={remove}><Trash2 className="h-4 w-4" /> Eliminar campo</Button>
        </div>
      </div>
    </div>
  );
}
const F: React.FC<{ t: string; children: React.ReactNode }> = ({ t, children }) => (
  <div><label className="block text-xs font-semibold text-slate-400 mb-1.5">{t}</label>{children}</div>
);
