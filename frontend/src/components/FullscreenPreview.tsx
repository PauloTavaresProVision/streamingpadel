import React, { useEffect, useRef, useState } from "react";
import { X, Clock, Timer } from "lucide-react";
import { Court } from "../api";
import { Brand } from "../ui";

const FAMILY: Record<string, string> = {
  "Sans": "system-ui, sans-serif", "Serif": "Georgia, serif", "Monospace": "monospace",
  "DejaVu Sans": "'DejaVu Sans', sans-serif", "DejaVu Serif": "'DejaVu Serif', serif",
  "Liberation Sans": "'Liberation Sans', Arial, sans-serif", "Noto Sans": "'Noto Sans', sans-serif", "Impact": "Impact, sans-serif",
};

/**
 * Mostra EXACTAMENTE o que vai para o YouTube: a região do crop escalada a
 * 16:9 (1920×1080) + logo/texto/hora/cronómetro nas posições e estilos finais.
 * As posições dos overlays (guardadas em % do frame completo) são remapeadas
 * para coordenadas do output cortado.
 */
export const FullscreenPreview: React.FC<{ court: Court; snapshotUrl: string | null; onClose: () => void }> = ({ court, snapshotUrl, onClose }) => {
  const boxRef = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(1280);
  const [now, setNow] = useState(new Date());
  useEffect(() => { const i = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(i); }, []);
  useEffect(() => {
    const el = boxRef.current; if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth)); ro.observe(el); setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const crop = parseCrop(court.crop_region) || { x: 0, y: 0, w: 100, h: 100 };
  const scale = w / 1920;                          // px do output → px do preview
  const fontPx = Math.max(8, court.overlay_font_size * scale);
  const logoUrl = court.logo_path ? `/data/${court.logo_path}?t=${court.id}` : null;
  const clock = now.toLocaleTimeString("pt-PT", { hour12: court.clock_format === "12h", hour: "2-digit", minute: "2-digit" });
  const family = FAMILY[court.overlay_font_family] || FAMILY.Sans;

  // Posições já são % do OUTPUT (região cortada) → usadas directamente no box 16:9.
  const lp = parsePos(court.logo_position || "TopRight");
  const tp = parsePos(court.overlay_text_position || "BottomLeft");
  const cp = parsePos(court.clock_position || "TopRight");
  const mp = parsePos(court.timer_position || "BottomLeft");
  const logoW = court.logo_size_percent;   // % do output

  return (
    <div className="fixed inset-0 bg-black z-50 flex flex-col">
      <div className="flex items-center justify-between px-5 py-3 text-white/90">
        <span className="text-sm font-semibold">Pré-visualização — {court.name} (igual ao YouTube)</span>
        <button onClick={onClose} className="flex items-center gap-2 text-white/80 hover:text-white text-sm"><X className="h-5 w-5" /> Fechar</button>
      </div>
      <div className="flex-1 flex items-center justify-center p-4">
        <div ref={boxRef} className="relative bg-black overflow-hidden" style={{ aspectRatio: "16/9", width: "min(100%, calc((100vh - 80px) * 16 / 9))" }}>
          {snapshotUrl ? <img src={snapshotUrl} alt="" draggable={false} className="absolute" style={cropImg(crop)} />
            : <div className="absolute inset-0 flex items-center justify-center text-white/40">Sem imagem</div>}

          {court.show_logo && (logoUrl
            ? <img src={logoUrl} alt="" style={{ position: "absolute", left: `${lp.x}%`, top: `${lp.y}%`, width: `${logoW}%`, opacity: court.logo_opacity / 100 }} />
            : <div style={{ position: "absolute", left: `${lp.x}%`, top: `${lp.y}%`, transform: `scale(${scale * 1.4})`, transformOrigin: "top left" }}><Brand compact /></div>)}

          {court.show_text && court.overlay_text && (
            <div style={{ position: "absolute", left: `${tp.x}%`, top: `${tp.y}%`, color: court.overlay_font_color, background: court.text_bg_color || "rgba(0,0,0,.5)", opacity: court.overlay_opacity / 100, fontFamily: family, fontSize: fontPx, fontWeight: court.overlay_font_bold ? 700 : 600, fontStyle: court.overlay_font_italic ? "italic" : "normal", padding: `${fontPx * 0.2}px ${fontPx * 0.4}px`, borderRadius: 6, whiteSpace: "pre" }}>
              {court.overlay_text}
            </div>)}

          {court.show_clock && (
            <div style={{ position: "absolute", left: `${cp.x}%`, top: `${cp.y}%`, color: court.clock_color, background: court.clock_bg || "rgba(0,0,0,.5)", fontSize: fontPx, padding: `${fontPx * 0.2}px ${fontPx * 0.4}px`, borderRadius: 6, display: "flex", alignItems: "center", gap: fontPx * 0.3 }}>
              <Clock style={{ width: fontPx, height: fontPx, color: "#2dd4bf" }} /> {clock}
            </div>)}

          {court.show_timer && (
            <div style={{ position: "absolute", left: `${mp.x}%`, top: `${mp.y}%`, color: court.timer_color, background: court.timer_bg || "rgba(0,0,0,.5)", fontSize: fontPx, fontFamily: "monospace", padding: `${fontPx * 0.2}px ${fontPx * 0.4}px`, borderRadius: 6, display: "flex", alignItems: "center", gap: fontPx * 0.3 }}>
              <Timer style={{ width: fontPx, height: fontPx, color: "#2dd4bf" }} /> {court.timer_format === "MM:SS" ? "45:18" : "00:45:18"}
            </div>)}
        </div>
      </div>
      <div className="text-center text-xs text-white/40 pb-3">1920 × 1080 · o que vês é o que vai para o YouTube</div>
    </div>
  );
};

function parseCrop(s?: string | null) {
  if (!s) return null;
  const p = s.split(",").map((v) => parseFloat(v));
  if (p.length !== 4 || p.some((v) => isNaN(v))) return null;
  const [x, y, w, h] = p;
  if (w <= 0 || h <= 0) return null;
  return { x, y, w, h };
}
function cropImg(c: { x: number; y: number; w: number; h: number }): React.CSSProperties {
  if (c.x === 0 && c.y === 0 && c.w >= 99.5 && c.h >= 99.5) return { inset: 0, width: "100%", height: "100%", objectFit: "contain" };
  return { left: `-${(c.x * 100 / c.w).toFixed(2)}%`, top: `-${(c.y * 100 / c.h).toFixed(2)}%`, width: `${(100 * 100 / c.w).toFixed(2)}%`, height: `${(100 * 100 / c.h).toFixed(2)}%`, objectFit: "fill", maxWidth: "none", maxHeight: "none" };
}
function parsePos(p?: string): { x: number; y: number } {
  if (p?.includes(",")) { const [a, b] = p.split(","); const x = parseFloat(a), y = parseFloat(b); if (!isNaN(x) && !isNaN(y)) return { x, y }; }
  switch (p) {
    case "TopLeft": return { x: 3, y: 4 }; case "TopCenter": return { x: 40, y: 4 }; case "TopRight": return { x: 80, y: 4 };
    case "BottomLeft": return { x: 3, y: 86 }; case "BottomCenter": return { x: 40, y: 86 }; case "BottomRight": return { x: 80, y: 86 };
    default: return { x: 3, y: 4 };
  }
}
