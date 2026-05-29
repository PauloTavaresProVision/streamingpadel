import React, { useEffect, useState } from "react";
import { Youtube, Link as LinkIcon, Unlink, CheckCircle2, AlertTriangle } from "lucide-react";
import { api, YouTubeStatus } from "../api";
import { Button, Card } from "../ui";

export default function Config() {
  const [yt, setYt] = useState<YouTubeStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const t = (m: string) => { setToast(m); setTimeout(() => setToast(""), 2600); };

  const load = async () => { try { setYt(await api.ytStatus()); } catch {} };
  useEffect(() => { load(); }, []);

  const connect = async () => {
    setBusy(true);
    try {
      const { auth_url } = await api.ytAuthUrl();
      const popup = window.open(auth_url, "yt-oauth", "width=560,height=720");
      const onMsg = async (ev: MessageEvent) => {
        if (ev?.data?.type === "youtube-oauth-result") {
          window.removeEventListener("message", onMsg); await load();
          t(ev.data.success ? "Conta YouTube ligada" : "Falha ao ligar");
          try { popup?.close(); } catch {}
        }
      };
      window.addEventListener("message", onMsg);
    } catch (e: any) { t("Erro: " + e.message); } finally { setBusy(false); }
  };
  const disconnect = async () => { if (!confirm("Desligar a conta YouTube?")) return; setBusy(true); try { await api.ytDisconnect(); await load(); t("Desligada"); } catch (e: any) { t("Erro: " + e.message); } finally { setBusy(false); } };

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <h1 className="text-3xl font-extrabold text-white mb-1">Configurações</h1>
      <p className="text-slate-400 text-sm mb-6">Liga a conta YouTube para criar transmissões automaticamente.</p>

      <Card className="p-6">
        <div className="flex items-center gap-2 mb-4"><Youtube className="h-5 w-5 text-red-500" /><h2 className="font-semibold text-white">Conta YouTube</h2></div>
        {!yt ? <p className="text-slate-500 text-sm">A carregar...</p>
          : !yt.is_server_configured ? (
            <div className="flex items-start gap-2 p-4 rounded-xl bg-amber-500/10 border border-amber-500/30">
              <AlertTriangle className="h-5 w-5 text-amber-400 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-amber-300"><p className="font-medium">Servidor sem credenciais Google</p><p className="text-amber-400/80 mt-1">Define <code>YOUTUBE_CLIENT_ID</code>, <code>YOUTUBE_CLIENT_SECRET</code> e <code>YOUTUBE_REDIRECT_URI</code> no <code>.env</code> do Jetson.</p></div>
            </div>
          ) : yt.is_connected ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/15 text-emerald-400 text-xs font-bold border border-emerald-500/30"><CheckCircle2 className="h-3.5 w-3.5" /> Ligado</span>
                <div><div className="font-semibold text-sm text-white">{yt.channel_title || "(canal)"}</div><div className="text-xs text-slate-500">{yt.channel_id}</div></div>
              </div>
              <Button variant="outline" onClick={disconnect} disabled={busy}><Unlink className="h-4 w-4" /> Desligar</Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-slate-400">Nenhuma conta ligada.</p>
              <Button variant="danger" onClick={connect} disabled={busy}><LinkIcon className="h-4 w-4" /> Ligar conta YouTube</Button>
            </div>
          )}
      </Card>
      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-slate-800 border border-slate-700 text-white px-5 py-3 rounded-xl text-sm">{toast}</div>}
    </div>
  );
}
