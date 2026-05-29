import React, { useEffect, useState } from "react";
import { Check, Camera, ArrowRight, Save, Loader2 } from "lucide-react";
import { api, Court } from "../api";
import { Button, Card } from "../ui";

const STEPS = [
  { n: 1, t: "Dados da transmissão", s: "Informações básicas" },
  { n: 2, t: "Escolher câmara", s: "Selecione a sua câmara" },
  { n: 3, t: "Personalização", s: "Overlay e identidade" },
  { n: 4, t: "YouTube", s: "Configurações de destino" },
  { n: 5, t: "Pré-visualização", s: "Revise e publique" },
];

/** Wizard de criação. Passos 1-2 aqui; ao continuar, cria o broadcast e abre o Editor (passos 3-5). */
export default function Wizard({ onDone }: { onDone: (court: Court | null) => void }) {
  const [courts, setCourts] = useState<Court[]>([]);
  const [title, setTitle] = useState("Jogo 1 - Quartos de Final");
  const [event, setEvent] = useState("");
  const [desc, setDesc] = useState("");
  const [privacy, setPrivacy] = useState("unlisted");
  const [selId, setSelId] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { api.listCourts().then((cs) => { setCourts(cs); if (cs[0]) setSelId(cs[0].id); }); }, []);

  const cont = async () => {
    if (!selId) { setErr("Escolhe uma câmara"); return; }
    setBusy(true); setErr("");
    try {
      // Cria broadcast no YouTube para o court escolhido (se conta ligada); senão segue só p/ editor.
      try { await api.createBroadcast(selId, { title, description: desc, privacy }); } catch (e: any) {
        // sem conta YouTube ligada — continua na mesma para o editor
        if (!/não ligada|not connected|configurad/i.test(e.message || "")) throw e;
      }
      const court = await api.getCourt(selId);
      onDone(court);
    } catch (e: any) { setErr(e.message); setBusy(false); }
  };

  return (
    <div className="p-8 max-w-[1500px] mx-auto">
      <h1 className="text-3xl font-extrabold text-white mb-1">Criar nova transmissão</h1>
      <p className="text-slate-400 text-sm mb-6">Siga os passos para configurar e iniciar a sua transmissão em directo.</p>

      {/* Stepper */}
      <div className="flex items-center gap-2 mb-8 overflow-x-auto">
        {STEPS.map((st, i) => (
          <React.Fragment key={st.n}>
            <div className="flex items-center gap-3 flex-shrink-0">
              <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${st.n <= 2 ? "bg-teal-500 text-slate-900" : "bg-slate-800 text-slate-500 border border-slate-700"}`}>{st.n === 1 ? "1" : st.n}</span>
              <div className="leading-tight">
                <div className={`text-sm font-semibold ${st.n <= 2 ? "text-teal-300" : "text-slate-500"}`}>{st.t}</div>
                <div className="text-[11px] text-slate-600">{st.s}</div>
              </div>
            </div>
            {i < STEPS.length - 1 && <div className="flex-1 border-t border-dashed border-slate-700 min-w-[20px]" />}
          </React.Fragment>
        ))}
      </div>

      <div className="grid lg:grid-cols-2 gap-6 items-start">
        {/* Dados */}
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-4"><span className="w-7 h-7 rounded-full bg-teal-500 text-slate-900 flex items-center justify-center text-sm font-bold">1</span><span className="font-bold text-white">Dados da transmissão</span></div>
          <Lbl t="Nome da transmissão *"><input className="inp" value={title} onChange={(e) => setTitle(e.target.value)} /></Lbl>
          <Lbl t="Evento"><input className="inp" placeholder="Torneio Feminino" value={event} onChange={(e) => setEvent(e.target.value)} /></Lbl>
          <Lbl t="Descrição"><textarea className="inp" rows={3} value={desc} onChange={(e) => setDesc(e.target.value)} /></Lbl>
          <Lbl t="Privacidade"><select className="inp" value={privacy} onChange={(e) => setPrivacy(e.target.value)}><option value="public" className="bg-slate-900">Pública</option><option value="unlisted" className="bg-slate-900">Não listada</option><option value="private" className="bg-slate-900">Privada</option></select></Lbl>
        </Card>

        {/* Câmaras */}
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-4"><span className="w-7 h-7 rounded-full bg-teal-500 text-slate-900 flex items-center justify-center text-sm font-bold">2</span><span className="font-bold text-white">Escolher câmara</span></div>
          <div className="grid sm:grid-cols-2 gap-3">
            {courts.map((c) => {
              const sel = selId === c.id;
              return (
                <button key={c.id} onClick={() => setSelId(c.id)} className={`text-left rounded-xl border overflow-hidden transition ${sel ? "border-teal-500 ring-2 ring-teal-500/30" : "border-slate-800 hover:border-slate-700"}`}>
                  <div className="relative aspect-video bg-slate-800">
                    <img src={api.snapshotUrl(c.id)} alt="" className="w-full h-full object-cover" onError={(e) => ((e.currentTarget as HTMLImageElement).style.opacity = "0")} />
                    <span className="absolute top-2 left-2"><Camera className="h-4 w-4 text-white/70" /></span>
                    <span className="absolute top-2 right-2 text-[10px] font-bold text-emerald-400 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Online</span>
                    {sel && <span className="absolute bottom-2 right-2 w-5 h-5 rounded-full bg-teal-500 text-slate-900 flex items-center justify-center"><Check className="h-3 w-3" /></span>}
                  </div>
                  <div className="p-3"><div className="text-sm font-semibold text-white">{c.name}</div><div className="text-xs text-slate-500">{c.camera_ip} · {c.resolution}</div></div>
                </button>
              );
            })}
          </div>
        </Card>
      </div>

      {err && <p className="text-red-400 text-sm mt-4">{err}</p>}
      <div className="flex justify-between mt-6">
        <Button variant="outline" onClick={() => onDone(null)}>Cancelar</Button>
        <Button variant="primary" onClick={cont} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />} Continuar</Button>
      </div>
    </div>
  );
}
const Lbl: React.FC<{ t: string; children: React.ReactNode }> = ({ t, children }) => (
  <div className="mb-3"><label className="block text-xs font-semibold text-slate-400 mb-1.5">{t}</label>{children}</div>
);
