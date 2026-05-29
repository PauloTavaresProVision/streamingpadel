import React, { useState } from "react";
import { Lock } from "lucide-react";
import { api } from "../api";
import { Button } from "../ui";

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [pwd, setPwd] = useState("");
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
    <div className="min-h-full flex items-center justify-center p-6">
      <form onSubmit={submit} className="bg-white border border-slate-200 rounded-2xl shadow-lg p-8 w-full max-w-sm">
        <div className="flex justify-center mb-4">
          <img src="/data/logos/gamevision.png" alt="GameVision" className="h-16 w-auto"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
        </div>
        <p className="text-sm text-slate-500 text-center mb-6">Inicia sessão para continuar</p>

        <label className="block text-xs font-semibold text-slate-500 mb-1.5">Password</label>
        <div className="relative">
          <Lock className="h-4 w-4 absolute left-3 top-3 text-slate-400" />
          <input type="password" autoFocus value={pwd} onChange={(e) => setPwd(e.target.value)}
            className="w-full pl-9 pr-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            placeholder="••••••••" />
        </div>
        {err && <p className="text-red-600 text-xs mt-2">{err}</p>}

        <Button type="submit" disabled={busy} className="w-full mt-5">{busy ? "A entrar..." : "Entrar"}</Button>
      </form>
    </div>
  );
}
