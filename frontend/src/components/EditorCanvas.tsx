import React, { useRef, useState, useEffect } from "react";
import { Clock, Timer } from "lucide-react";
import { Court } from "../api";
import { Brand } from "../ui";

interface Props {
  court: Court;
  snapshotUrl: string | null;
  patch: (k: keyof Court, v: any) => void;
}

/**
 * Canvas interactivo do editor: imagem da câmara + frame de crop arrastável
 * (8 alças) + logo arrastável/redimensionável + texto/hora/cronómetro arrastáveis.
 * Todas as posições em % do canvas; o que vês corresponde ao output.
 */
export const EditorCanvas: React.FC<Props> = ({ court, snapshotUrl, patch }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState(new Date());
  useEffect(() => { const i = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(i); }, []);

  const rect = () => ref.current!.getBoundingClientRect();
  const pctX = (clientX: number) => Math.max(0, Math.min(100, ((clientX - rect().left) / rect().width) * 100));
  const pctY = (clientY: number) => Math.max(0, Math.min(100, ((clientY - rect().top) / rect().height) * 100));

  // ---- Crop ----
  const crop = parseCrop(court.crop_region) || { x: 4, y: 4, w: 92, h: 92 };
  const dragCrop = useRef<{ mode: string; sx: number; sy: number; init: typeof crop } | null>(null);
  const cropDown = (mode: string) => (e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    dragCrop.current = { mode, sx: e.clientX, sy: e.clientY, init: { ...crop } };
  };
  const cropMove = (e: React.PointerEvent) => {
    if (!dragCrop.current) return;
    const { mode, sx, sy, init } = dragCrop.current;
    const dx = ((e.clientX - sx) / rect().width) * 100, dy = ((e.clientY - sy) / rect().height) * 100;
    let n = { ...init };
    const cl = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, hi));
    if (mode === "move") { n.x = cl(init.x + dx, 0, 100 - init.w); n.y = cl(init.y + dy, 0, 100 - init.h); }
    if (mode.includes("w")) { const nx = cl(init.x + dx, 0, init.x + init.w - 10); n.w = init.x + init.w - nx; n.x = nx; }
    if (mode.includes("e")) { n.w = cl(init.w + dx, 10, 100 - init.x); }
    if (mode.includes("n")) { const ny = cl(init.y + dy, 0, init.y + init.h - 10); n.h = init.y + init.h - ny; n.y = ny; }
    if (mode.includes("s")) { n.h = cl(init.h + dy, 10, 100 - init.y); }
    patch("crop_region", `${n.x.toFixed(1)},${n.y.toFixed(1)},${n.w.toFixed(1)},${n.h.toFixed(1)}`);
  };
  const endDrag = (e: React.PointerEvent) => { dragCrop.current = null; try { (e.target as HTMLElement).releasePointerCapture(e.pointerId); } catch {} };

  const clock = now.toLocaleTimeString("pt-PT", { hour12: court.clock_format === "12h", hour: "2-digit", minute: "2-digit" });
  const logoUrl = court.logo_path ? `/data/${court.logo_path}?t=${court.id}` : null;

  return (
    <div ref={ref} className="relative w-full aspect-video bg-black rounded-xl overflow-hidden select-none" style={{ touchAction: "none" }}
      onPointerMove={cropMove} onPointerUp={endDrag} onPointerCancel={endDrag}>
      {snapshotUrl ? <img src={snapshotUrl} alt="" draggable={false} className="absolute inset-0 w-full h-full object-contain pointer-events-none" />
        : <div className="absolute inset-0 flex items-center justify-center text-slate-600 text-sm">Sem imagem</div>}

      {/* Máscara fora do crop */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute bg-black/45" style={{ left: 0, top: 0, right: 0, height: `${crop.y}%` }} />
        <div className="absolute bg-black/45" style={{ left: 0, top: `${crop.y + crop.h}%`, right: 0, bottom: 0 }} />
        <div className="absolute bg-black/45" style={{ left: 0, top: `${crop.y}%`, width: `${crop.x}%`, height: `${crop.h}%` }} />
        <div className="absolute bg-black/45" style={{ left: `${crop.x + crop.w}%`, top: `${crop.y}%`, right: 0, height: `${crop.h}%` }} />
      </div>

      {/* Frame de crop arrastável */}
      <div className="absolute border-2 border-dashed border-white/80" style={{ left: `${crop.x}%`, top: `${crop.y}%`, width: `${crop.w}%`, height: `${crop.h}%`, cursor: "move" }}
        onPointerDown={cropDown("move")}>
        {[["nw", "-top-1.5 -left-1.5 cursor-nwse-resize"], ["n", "-top-1.5 left-1/2 -translate-x-1/2 cursor-ns-resize"], ["ne", "-top-1.5 -right-1.5 cursor-nesw-resize"],
          ["w", "top-1/2 -left-1.5 -translate-y-1/2 cursor-ew-resize"], ["e", "top-1/2 -right-1.5 -translate-y-1/2 cursor-ew-resize"],
          ["sw", "-bottom-1.5 -left-1.5 cursor-nesw-resize"], ["s", "-bottom-1.5 left-1/2 -translate-x-1/2 cursor-ns-resize"], ["se", "-bottom-1.5 -right-1.5 cursor-nwse-resize"]].map(([m, cls]) => (
          <span key={m} onPointerDown={cropDown(m)} className={`absolute ${cls} w-3 h-3 rounded-full bg-white border border-slate-400`} />
        ))}
      </div>

      {/* Logo (arrastar + redimensionar) */}
      {court.show_logo && (
        <Draggable canvas={ref} pos={court.logo_position} onMove={(p) => patch("logo_position", p)}
          style={{ width: `${court.logo_size_percent}%`, opacity: court.logo_opacity / 100 }} resizable
          onResize={(clientX) => { const w = Math.max(5, Math.min(40, pctX(clientX) - parsePos(court.logo_position).x)); patch("logo_size_percent", Math.round(w)); }}>
          {logoUrl ? <img src={logoUrl} draggable={false} className="w-full h-auto pointer-events-none" /> : <div className="pointer-events-none"><Brand compact /></div>}
        </Draggable>
      )}

      {/* Texto */}
      {court.show_text && court.overlay_text && (
        <Draggable canvas={ref} pos={court.overlay_text_position} onMove={(p) => patch("overlay_text_position", p)}>
          <div className="px-4 py-2 rounded-lg border border-teal-400/70 whitespace-pre pointer-events-none"
            style={{ color: court.overlay_font_color, background: court.text_bg_color || "rgba(0,0,0,.5)", opacity: court.overlay_opacity / 100, fontWeight: court.overlay_font_bold ? 700 : 600, fontStyle: court.overlay_font_italic ? "italic" : "normal" }}>
            {court.overlay_text}
          </div>
        </Draggable>
      )}

      {/* Hora */}
      {court.show_clock && (
        <Draggable canvas={ref} pos={court.clock_position} onMove={(p) => patch("clock_position", p)}>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-teal-400/70 pointer-events-none" style={{ color: court.clock_color, background: court.clock_bg || "rgba(0,0,0,.5)" }}>
            <Clock className="h-4 w-4 text-teal-400" /> {clock}
          </div>
        </Draggable>
      )}

      {/* Cronómetro */}
      {court.show_timer && (
        <Draggable canvas={ref} pos={court.timer_position} onMove={(p) => patch("timer_position", p)}>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-teal-400/70 font-mono pointer-events-none" style={{ color: court.timer_color, background: court.timer_bg || "rgba(0,0,0,.5)" }}>
            <Timer className="h-4 w-4 text-teal-400" /> {court.timer_format === "MM:SS" ? "45:18" : "00:45:18"}
          </div>
        </Draggable>
      )}
    </div>
  );
};

/** Elemento arrastável posicionado em % do canvas (com resize opcional). */
const Draggable: React.FC<{
  canvas: React.RefObject<HTMLDivElement>; pos: string; onMove: (p: string) => void;
  style?: React.CSSProperties; children: React.ReactNode; resizable?: boolean; onResize?: (clientX: number) => void;
}> = ({ canvas, pos, onMove, style, children, resizable, onResize }) => {
  const { x, y } = parsePos(pos);
  const dragging = useRef<"move" | "resize" | null>(null);
  const start = (mode: "move" | "resize") => (e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture(e.pointerId); dragging.current = mode;
  };
  const move = (e: React.PointerEvent) => {
    if (!canvas.current) return;
    const r = canvas.current.getBoundingClientRect();
    if (dragging.current === "move") {
      const nx = Math.max(0, Math.min(95, ((e.clientX - r.left) / r.width) * 100));
      const ny = Math.max(0, Math.min(95, ((e.clientY - r.top) / r.height) * 100));
      onMove(`${nx.toFixed(1)},${ny.toFixed(1)}`);
    } else if (dragging.current === "resize") { onResize?.(e.clientX); }
  };
  const end = (e: React.PointerEvent) => { dragging.current = null; try { (e.target as HTMLElement).releasePointerCapture(e.pointerId); } catch {} };
  return (
    <div className="absolute group" style={{ left: `${x}%`, top: `${y}%`, cursor: "grab", ...style }}
      onPointerDown={start("move")} onPointerMove={move} onPointerUp={end} onPointerCancel={end}>
      {children}
      <div className="absolute inset-0 border border-dashed border-teal-400 opacity-0 group-hover:opacity-70 pointer-events-none rounded" />
      {resizable && <div onPointerDown={start("resize")} className="absolute -right-2 -bottom-2 w-4 h-4 bg-teal-500 border-2 border-white rounded-full opacity-0 group-hover:opacity-100" style={{ cursor: "nwse-resize" }} />}
    </div>
  );
};

function parseCrop(s?: string | null) {
  if (!s) return null;
  const p = s.split(",").map((v) => parseFloat(v));
  if (p.length !== 4 || p.some((v) => isNaN(v))) return null;
  return { x: p[0], y: p[1], w: p[2], h: p[3] };
}
function parsePos(p?: string): { x: number; y: number } {
  if (p?.includes(",")) { const [a, b] = p.split(","); const x = parseFloat(a), y = parseFloat(b); if (!isNaN(x) && !isNaN(y)) return { x, y }; }
  switch (p) {
    case "TopLeft": return { x: 3, y: 4 };
    case "TopCenter": return { x: 40, y: 4 };
    case "TopRight": return { x: 80, y: 4 };
    case "BottomLeft": return { x: 3, y: 86 };
    case "BottomCenter": return { x: 40, y: 86 };
    case "BottomRight": return { x: 80, y: 86 };
    default: return { x: 3, y: 4 };
  }
}
