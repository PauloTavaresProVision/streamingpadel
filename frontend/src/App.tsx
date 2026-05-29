import React, { useState } from "react";
import { Tv, LayoutGrid, Settings, LogOut } from "lucide-react";
import { auth } from "./api";
import { BrandLogo } from "./ui";
import Login from "./views/Login";
import Transmissoes from "./views/Transmissoes";
import Campos from "./views/Campos";
import Config from "./views/Config";

type View = "transmissoes" | "campos" | "config";

const NAV: { id: View; label: string; icon: any }[] = [
  { id: "transmissoes", label: "Transmissões", icon: Tv },
  { id: "campos", label: "Campos", icon: LayoutGrid },
  { id: "config", label: "Configuração", icon: Settings },
];

export default function App() {
  const [authed, setAuthed] = useState(auth.isAuthed());
  const [view, setView] = useState<View>("transmissoes");

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  return (
    <div className="min-h-full flex">
      {/* Sidebar */}
      <aside className="w-60 bg-slate-900 text-slate-300 flex flex-col fixed inset-y-0 left-0">
        <div className="flex items-center px-5 py-5 border-b border-slate-800">
          <BrandLogo className="h-8" />
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map((n) => {
            const Icon = n.icon;
            const active = view === n.id;
            return (
              <button key={n.id} onClick={() => setView(n.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${active ? "bg-blue-600 text-white" : "text-slate-300 hover:bg-slate-800"}`}>
                <Icon className="h-4 w-4" /> {n.label}
              </button>
            );
          })}
        </nav>
        <div className="p-3 border-t border-slate-800">
          <div className="flex items-center gap-2 px-2 py-2 text-sm">
            <span className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold">A</span>
            <span>admin</span>
          </div>
          <button onClick={() => { auth.clear(); setAuthed(false); }}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-400 hover:bg-slate-800 mt-1">
            <LogOut className="h-4 w-4" /> Sair
          </button>
        </div>
      </aside>

      {/* Conteúdo */}
      <main className="flex-1 ml-60 min-h-full">
        {view === "transmissoes" && <Transmissoes />}
        {view === "campos" && <Campos />}
        {view === "config" && <Config />}
      </main>
    </div>
  );
}
