import React, { useEffect, useState } from "react";
import { Plus, Save, Trash2, Camera } from "lucide-react";
import { api, Court } from "../api";
import { Button, Card } from "../ui";

export default function Campos() {
  const [courts, setCourts] = useState<Court[]>([]);
  const [sel, setSel] = useState<Court | null>(null);
  const [toast, setToast] = useState("");
  const t = (m: string) => { setToast(m); setTimeout(() => setToast(""), 2500); };

  const load = async () => {
    const cs = await api.listCourts();
    setCourts(cs);
    setSel((s) => (s ? cs.find((c) => c.id === s.id) || cs[0] : cs[0]) || null);
  };
  useEffect(() => { load(); }, []);

  const patch = (k: keyof Court, v: any) => setSel((c) => (c ? { ...c, [k]: v } : c));
  const save = async () => { if (!sel) return; try { await api.updateCourt(sel.id, sel); await load(); t("Câmara guardada"); } catch (e: any) { t("Erro: " + e.message); } };
  const create = async () => { const name = prompt("Nome do novo campo:"); if (!name) return; const c = await api.createCourt(name); await load(); setSel(c); };
  const remove = async () => { if (!sel || !confirm(`Eliminar "${sel.name}"?`)) return; await api.deleteCourt(sel.id); setSel(null); await load(); };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div><h1 className="text-3xl font-extrabold text-white">Câmaras</h1><p className="text-slate-400 text-sm mt-1">Configuração das câmaras de cada campo.</p></div>
        <Button variant="primary" onClick={create}><Plus className="h-4 w-4" /> Novo campo</Button>
      </div>

      <div className="grid md:grid-cols-[260px_1fr] gap-6 items-start">
        <div className="space-y-1.5">
          {courts.map((c) => (
            <button key={c.id} onClick={() => setSel(c)}
              className={`w-full text-left px-4 py-3 rounded-xl border transition flex items-center gap-3 ${sel?.id === c.id ? "bg-teal-500/10 border-teal-500/40" : "bg-slate-900/60 border-slate-800 hover:border-slate-700"}`}>
              <Camera className="h-4 w-4 text-slate-500" />
              <div><div className="font-semibold text-sm text-white">{c.name}</div><div className="text-xs text-slate-500">{c.camera_ip || "sem IP"}</div></div>
            </button>
          ))}
        </div>

        {sel && (
          <Card className="p-6 space-y-4">
            <F t="Nome do campo"><input className="inp" value={sel.name} onChange={(e) => patch("name", e.target.value)} /></F>
            <div className="flex gap-4">
              <F t="IP da câmara"><input className="inp" value={sel.camera_ip} onChange={(e) => patch("camera_ip", e.target.value)} /></F>
              <F t="Caminho RTSP"><input className="inp" value={sel.rtsp_path ?? ""} placeholder="/Streaming/Channels/101" onChange={(e) => patch("rtsp_path", e.target.value)} /></F>
            </div>
            <div className="flex gap-4">
              <F t="Utilizador"><input className="inp" value={sel.nvr_user} onChange={(e) => patch("nvr_user", e.target.value)} /></F>
              <F t="Password"><input type="password" className="inp" value={sel.nvr_password} onChange={(e) => patch("nvr_password", e.target.value)} /></F>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="teal" onClick={save}><Save className="h-4 w-4" /> Guardar</Button>
              <Button variant="outline" onClick={remove}><Trash2 className="h-4 w-4" /> Eliminar</Button>
            </div>
          </Card>
        )}
      </div>
      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-800 border border-slate-700 text-white px-5 py-3 rounded-xl text-sm">{toast}</div>}
    </div>
  );
}
const F: React.FC<{ t: string; children: React.ReactNode }> = ({ t, children }) => (
  <div className="flex-1"><label className="block text-xs font-semibold text-slate-400 mb-1.5">{t}</label>{children}</div>
);
