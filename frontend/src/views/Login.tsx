import React, { useState } from "react";
import { Lock, Mail, Eye, EyeOff, Radio, MonitorPlay, TrendingUp, Globe, ArrowRight } from "lucide-react";
import { api } from "../api";
import { Brand } from "../ui";

const FEATURES = [
  { icon: Radio, t: "Transmissões em directo", s: "Gestão completa de eventos e câmaras." },
  { icon: MonitorPlay, t: "Qualidade profissional", s: "Vídeo em alta definição, estável e fiável." },
  { icon: TrendingUp, t: "Métricas em tempo real", s: "Acompanhe o desempenho das transmissões." },
];

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [pwd, setPwd] = useState("");
  const [email, setEmail] = useState("");
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(true);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try { await api.login(pwd); onLogin(); }
    catch (e: any) { setErr(e.message || "Falha no login"); }
    finally { setBusy(false); }
  };

  return (
    <div className="min-h-full grid lg:grid-cols-2 bg-[#070b14]">
      {/* Hero esquerdo */}
      <div className="relative hidden lg:flex flex-col justify-between p-12 overflow-hidden border-r border-slate-800/60">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-[#0a1424] to-[#070b14]" />
        <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: "radial-gradient(circle at 70% 30%, #2dd4bf, transparent 60%)" }} />
        <div className="relative">
          <Brand />
          <h1 className="text-4xl font-extrabold text-white mt-16 leading-tight">Gestão moderna de<br /><span className="text-teal-400">transmissões de padel</span></h1>
          <p className="text-slate-400 mt-4 max-w-md">Controle, personalize e transmita cada jogo com qualidade profissional. Tudo numa única plataforma.</p>
          <div className="mt-10 space-y-3 max-w-md">
            {FEATURES.map((f, i) => {
              const Icon = f.icon;
              return (
                <div key={i} className="flex items-center gap-4 p-4 rounded-2xl bg-slate-900/40 border border-slate-800">
                  <span className="w-10 h-10 rounded-xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center"><Icon className="h-5 w-5 text-teal-400" /></span>
                  <div><div className="font-semibold text-white text-sm">{f.t}</div><div className="text-xs text-slate-500">{f.s}</div></div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="relative text-[11px] text-slate-600">© 2025 Padel Live</div>
      </div>

      {/* Login direito */}
      <div className="flex items-center justify-center p-6 lg:p-12">
        <form onSubmit={submit} className="w-full max-w-md bg-slate-900/50 border border-slate-800 rounded-3xl p-8 lg:p-10">
          <div className="flex justify-center mb-5">
            <span className="w-16 h-16 rounded-2xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center"><Lock className="h-7 w-7 text-teal-400" /></span>
          </div>
          <h2 className="text-3xl font-extrabold text-white text-center">Entrar</h2>
          <p className="text-slate-400 text-center text-sm mt-1 mb-7">Aceda à plataforma de gestão de transmissões</p>

          <label className="block text-sm font-semibold text-slate-300 mb-1.5">Email</label>
          <div className="relative mb-4">
            <Mail className="h-4 w-4 absolute left-3 top-3.5 text-slate-500" />
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="inp pl-9" placeholder="exemplo@padellive.pt" />
          </div>

          <label className="block text-sm font-semibold text-slate-300 mb-1.5">Password</label>
          <div className="relative">
            <Lock className="h-4 w-4 absolute left-3 top-3.5 text-slate-500" />
            <input type={show ? "text" : "password"} autoFocus value={pwd} onChange={(e) => setPwd(e.target.value)} className="inp pl-9 pr-10" placeholder="A sua password" />
            <button type="button" onClick={() => setShow(!show)} className="absolute right-3 top-3.5 text-slate-500 hover:text-slate-300">{show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button>
          </div>

          <div className="flex items-center justify-between mt-4 mb-5">
            <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="accent-teal-400 w-4 h-4 rounded" /> Lembrar-me
            </label>
            <span className="text-sm text-teal-400/80">Esqueceu-se da password?</span>
          </div>

          {err && <p className="text-red-400 text-sm mb-3 text-center">{err}</p>}

          <button type="submit" disabled={busy} className="w-full py-3.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold flex items-center justify-center gap-2 shadow-lg shadow-blue-600/20 disabled:opacity-50">
            <ArrowRight className="h-5 w-5" /> {busy ? "A entrar..." : "Entrar"}
          </button>
          <button type="button" className="w-full py-3.5 mt-3 rounded-xl bg-slate-800/60 border border-slate-700 text-slate-300 font-semibold flex items-center justify-center gap-2 hover:border-slate-600">
            <Globe className="h-5 w-5" /> Voltar ao site
          </button>

          <div className="mt-6 pt-5 border-t border-slate-800 text-center text-xs text-slate-500 flex items-center justify-center gap-1.5">
            <Lock className="h-3.5 w-3.5" /> Acesso reservado ao administrador
          </div>
        </form>
      </div>
    </div>
  );
}
