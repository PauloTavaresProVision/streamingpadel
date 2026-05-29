import React from "react";
import { X } from "lucide-react";
import { Court } from "../api";
import { OverlayText } from "./OverlayText";

/**
 * Mostra o resultado final (imagem cortada + logo + texto/hora) num 16:9 grande
 * a ocupar o ecrã, para o utilizador confirmar como vai ficar no YouTube.
 */
export const FullscreenPreview: React.FC<{ court: Court; snapshotUrl: string | null; onClose: () => void }> = ({
  court, snapshotUrl, onClose,
}) => {
  const crop = cropStyles(court.crop_region ?? undefined);
  const xy = parsePos(court.logo_position);
  const logoUrl = court.logo_path ? `/data/${court.logo_path}?t=${court.id}` : null;

  return (
    <div className="fixed inset-0 bg-black z-50 flex flex-col">
      <div className="flex items-center justify-between px-5 py-3 text-white/90">
        <span className="text-sm font-semibold">Pré-visualização — {court.name} (como vai ficar no YouTube)</span>
        <button onClick={onClose} className="flex items-center gap-2 text-white/80 hover:text-white text-sm">
          <X className="h-5 w-5" /> Fechar
        </button>
      </div>
      <div className="flex-1 flex items-center justify-center p-4">
        <div className="relative bg-black overflow-hidden" style={{ aspectRatio: "16/9", width: "min(100%, calc((100vh - 80px) * 16 / 9))" }}>
          {snapshotUrl ? (
            <img src={snapshotUrl} alt="" className="absolute" draggable={false}
              style={crop ?? { inset: 0, width: "100%", height: "100%", objectFit: "contain" }} />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-white/40">Sem imagem</div>
          )}
          {logoUrl && (
            <img src={logoUrl} alt="logo" draggable={false}
              style={{ position: "absolute", left: `${xy.x}%`, top: `${xy.y}%`, width: `${court.logo_size_percent}%`, opacity: court.logo_opacity / 100 }} />
          )}
          <OverlayText text={court.overlay_text} showClock={court.show_clock} position={court.overlay_text_position}
            fontSize={court.overlay_font_size} fontColor={court.overlay_font_color} fontFamily={court.overlay_font_family}
            bold={court.overlay_font_bold} italic={court.overlay_font_italic} bg={court.overlay_bg} />
        </div>
      </div>
    </div>
  );
};

function cropStyles(cropRegion?: string): React.CSSProperties | null {
  if (!cropRegion) return null;
  const p = cropRegion.split(",").map((v) => parseFloat(v));
  if (p.length !== 4 || p.some((v) => isNaN(v))) return null;
  const [x, y, w, h] = p;
  if (w <= 0 || h <= 0) return null;
  if (x === 0 && y === 0 && w >= 99.5 && h >= 99.5) return null;
  return {
    left: `-${((x * 100) / w).toFixed(2)}%`, top: `-${((y * 100) / h).toFixed(2)}%`,
    width: `${((100 * 100) / w).toFixed(2)}%`, height: `${((100 * 100) / h).toFixed(2)}%`,
    objectFit: "fill", maxWidth: "none", maxHeight: "none",
  };
}
function parsePos(position: string): { x: number; y: number } {
  if (position?.includes(",")) {
    const [xs, ys] = position.split(",");
    const x = parseFloat(xs), y = parseFloat(ys);
    if (!isNaN(x) && !isNaN(y)) return { x, y };
  }
  switch (position) {
    case "TopLeft": return { x: 3, y: 3 };
    case "TopRight": return { x: 87, y: 3 };
    case "BottomLeft": return { x: 3, y: 87 };
    case "BottomRight": return { x: 87, y: 87 };
    default: return { x: 87, y: 3 };
  }
}
