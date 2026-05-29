import React, { useState } from "react";
import { Lock } from "lucide-react";
import { api } from "../api";
import { Button, Brand } from "../ui";

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
    <div className="min-h-full flex items-center justify-center p-6 bg-[#070b14]">
      <form onSubmit={submit} className="bg-slate-900/70 border border-slate-800 rounded-2xl shadow-2xl p-8 w-full max-w-sm">
        <div className="flex justify-center mb-6"><Brand /></div>
        <p className="text-sm text-slate-400 text-center mb-6">Inicia sessão para continuar</p>
        <label className="block text-xs font-semibold text-slate-400 mb-1.5">Password</label>
        <div className="relative">
          <Lock className="h-4 w-4 absolute left-3 top-3.5 text-slate-500" />
          <input type="password" autoFocus value={pwd} onChange={(e) => setPwd(e.target.value)}
            className="inp pl-9" placeholder="••••••••" />
        </div>
        {err && <p className="text-red-400 text-xs mt-2">{err}</p>}
        <Button type="submit" variant="teal" disabled={busy} className="w-full mt-5">{busy ? "A entrar..." : "Entrar"}</Button>
      </form>
    </div>
  );
}
