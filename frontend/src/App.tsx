import React, { useState } from "react";
import { LayoutGrid, Radio, Camera, Youtube, Image as ImageIcon, Settings } from "lucide-react";
import { auth } from "./api";
import { Brand, Sparkline } from "./ui";
import Login from "./views/Login";
import Dashboard from "./views/Dashboard";
import Transmissoes from "./views/Transmissoes";
import Campos from "./views/Campos";
import Config from "./views/Config";

type View = "dashboard" | "transmissoes" | "camaras" | "youtube" | "templates" | "config";

const NAV: { id: View; label: string; icon: any }[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutGrid },
  { id: "transmissoes", label: "Transmissões", icon: Radio },
  { id: "camaras", label: "Câmaras", icon: Camera },
  { id: "youtube", label: "YouTube", icon: Youtube },
  { id: "templates", label: "Logotipos e Templates", icon: ImageIcon },
  { id: "config", label: "Configurações", icon: Settings },
];

export default function App() {
  const [authed, setAuthed] = useState(auth.isAuthed());
  const [view, setView] = useState<View>("dashboard");

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  return (
    <div className="min-h-full flex bg-[#070b14] text-slate-300">
      {/* Sidebar */}
      <aside className="w-64 bg-[#0a0f1c] border-r border-slate-800/80 flex flex-col fixed inset-y-0 left-0">
        <div className="px-5 py-5"><Brand /></div>

        {/* Perfil */}
        <div className="mx-3 mb-2 flex items-center gap-3 px-3 py-3 rounded-xl bg-slate-900/60 border border-slate-800">
          <span className="w-10 h-10 rounded-full bg-gradient-to-br from-teal-400/30 to-cyan-500/30 border border-teal-500/30 flex items-center justify-center text-teal-300 font-bold">A</span>
          <div className="leading-tight">
            <div className="text-sm font-semibold text-white">Administrador</div>
            <div className="text-[11px] text-slate-400 flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Admin</div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
          {NAV.map((n) => {
            const Icon = n.icon; const active = view === n.id;
            return (
              <button key={n.id} onClick={() => setView(n.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition ${active ? "bg-teal-500/10 text-teal-300 border border-teal-500/20" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 border border-transparent"}`}>
                <Icon className="h-[18px] w-[18px]" /> {n.label}
              </button>
            );
          })}
        </nav>

        {/* Estado do sistema */}
        <div className="mx-3 mb-3 p-3 rounded-xl bg-slate-900/60 border border-slate-800">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200"><span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" /> Sistema operacional</div>
          <div className="text-[11px] text-slate-500 mt-0.5">Tudo operacional</div>
          <Sparkline />
        </div>

        <div className="px-5 py-3 border-t border-slate-800/80 flex items-center justify-between">
          <div className="text-[11px] text-slate-600">© 2025 Padel Live</div>
          <button onClick={() => { auth.clear(); setAuthed(false); }} className="text-[11px] text-slate-500 hover:text-teal-400">Sair</button>
        </div>
      </aside>

      {/* Conteúdo */}
      <main className="flex-1 ml-64 min-h-full">
        {view === "dashboard" && <Dashboard onNavigate={(v) => setView(v as View)} />}
        {view === "transmissoes" && <Transmissoes />}
        {view === "camaras" && <Campos />}
        {(view === "youtube" || view === "config" || view === "templates") && <Config />}
      </main>
    </div>
  );
}
