import React, { useEffect, useState } from "react";
import { Plus, Save, Trash2, Camera } from "lucide-react";
import { api, Court } from "../api";
import { Button } from "../ui";

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
  const save = async () => {
    if (!sel) return;
    try { await api.updateCourt(sel.id, sel); await load(); t("Câmara guardada"); }
    catch (e: any) { t("Erro: " + e.message); }
  };
  const create = async () => {
    const name = prompt("Nome do novo campo:");
    if (!name) return;
    const c = await api.createCourt(name); await load(); setSel(c);
  };
  const remove = async () => {
    if (!sel || !confirm(`Eliminar "${sel.name}"?`)) return;
    await api.deleteCourt(sel.id); setSel(null); await load();
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Campos</h1>
          <p className="text-slate-500 text-sm">Configuração das câmaras de cada campo.</p>
        </div>
        <Button onClick={create}><Plus className="h-4 w-4" /> Novo campo</Button>
      </div>

      <div className="grid md:grid-cols-[260px_1fr] gap-6 items-start">
        {/* lista */}
        <div className="space-y-1.5">
          {courts.map((c) => (
            <button key={c.id} onClick={() => setSel(c)}
              className={`w-full text-left px-4 py-3 rounded-xl border transition flex items-center gap-3 ${sel?.id === c.id ? "bg-blue-50 border-blue-300" : "bg-white border-slate-200 hover:border-slate-300"}`}>
              <Camera className="h-4 w-4 text-slate-400" />
              <div>
                <div className="font-semibold text-sm text-slate-800">{c.name}</div>
                <div className="text-xs text-slate-400">{c.camera_ip || "sem IP"}</div>
              </div>
            </button>
          ))}
        </div>

        {/* form */}
        {sel && (
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6 space-y-4">
            <Field label="Nome do campo"><input className="inp" value={sel.name} onChange={(e) => patch("name", e.target.value)} /></Field>
            <div className="flex gap-4">
              <Field label="IP da câmara"><input className="inp" value={sel.camera_ip} onChange={(e) => patch("camera_ip", e.target.value)} /></Field>
              <Field label="Caminho RTSP"><input className="inp" value={sel.rtsp_path ?? ""} placeholder="/Streaming/Channels/101" onChange={(e) => patch("rtsp_path", e.target.value)} /></Field>
            </div>
            <div className="flex gap-4">
              <Field label="Utilizador"><input className="inp" value={sel.nvr_user} onChange={(e) => patch("nvr_user", e.target.value)} /></Field>
              <Field label="Password"><input type="password" className="inp" value={sel.nvr_password} onChange={(e) => patch("nvr_password", e.target.value)} /></Field>
            </div>
            <div className="flex gap-3 pt-2">
              <Button onClick={save}><Save className="h-4 w-4" /> Guardar</Button>
              <Button variant="outline" className="text-red-600 border-red-200 hover:bg-red-50" onClick={remove}><Trash2 className="h-4 w-4" /> Eliminar</Button>
            </div>
          </div>
        )}
      </div>

      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-900 text-white px-5 py-3 rounded-xl text-sm">{toast}</div>}
      <style>{`.inp{width:100%;padding:9px 11px;border:1px solid #cbd5e1;border-radius:10px;font-size:14px;outline:none}.inp:focus{border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.12)}`}</style>
    </div>
  );
}
const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex-1"><label className="block text-xs font-semibold text-slate-500 mb-1.5">{label}</label>{children}</div>
);
