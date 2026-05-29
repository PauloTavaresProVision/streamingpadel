import React, { useRef, useState } from "react";
import { Button } from "../ui";
import { Crop, X, Loader2, ImageOff } from "lucide-react";

interface CropSelectorProps {
  snapshotUrl: string | null;
  isLoadingSnapshot: boolean;
  snapshotError: string | null;
  cropRegion: string;
  onCropChange: (newCropRegion: string) => void;
}

type DragMode = "none" | "move" | "resize-nw" | "resize-ne" | "resize-sw" | "resize-se";

export const CropSelector: React.FC<CropSelectorProps> = ({
  snapshotUrl,
  isLoadingSnapshot,
  snapshotError,
  cropRegion,
  onCropChange,
}) => {
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [dragMode, setDragMode] = useState<DragMode>("none");
  const dragStartRef = useRef<{ clientX: number; clientY: number; rect: DOMRect; initial: CropRect } | null>(null);

  const cropEnabled = !!cropRegion && cropRegion.split(",").length === 4;
  const current = cropEnabled ? parseCrop(cropRegion) : null;

  const handleEnable = () => onCropChange("10,10,80,80");
  const handleDisable = () => onCropChange("");

  const startDrag = (mode: DragMode, e: React.PointerEvent) => {
    if (!canvasRef.current || !current) return;
    e.preventDefault();
    e.stopPropagation();
    setDragMode(mode);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    dragStartRef.current = {
      clientX: e.clientX, clientY: e.clientY,
      rect: canvasRef.current.getBoundingClientRect(), initial: { ...current },
    };
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (dragMode === "none" || !dragStartRef.current) return;
    const { clientX, clientY, rect, initial } = dragStartRef.current;
    const dxPct = ((e.clientX - clientX) / rect.width) * 100;
    const dyPct = ((e.clientY - clientY) / rect.height) * 100;
    let next: CropRect = { ...initial };
    switch (dragMode) {
      case "move":
        next.x = clamp(initial.x + dxPct, 0, 100 - initial.w);
        next.y = clamp(initial.y + dyPct, 0, 100 - initial.h);
        break;
      case "resize-nw": {
        const newX = clamp(initial.x + dxPct, 0, initial.x + initial.w - 5);
        const newY = clamp(initial.y + dyPct, 0, initial.y + initial.h - 5);
        next.w = initial.x + initial.w - newX; next.h = initial.y + initial.h - newY;
        next.x = newX; next.y = newY; break;
      }
      case "resize-ne": {
        const newY = clamp(initial.y + dyPct, 0, initial.y + initial.h - 5);
        next.w = clamp(initial.w + dxPct, 5, 100 - initial.x);
        next.h = initial.y + initial.h - newY; next.y = newY; break;
      }
      case "resize-sw": {
        const newX = clamp(initial.x + dxPct, 0, initial.x + initial.w - 5);
        next.w = initial.x + initial.w - newX;
        next.h = clamp(initial.h + dyPct, 5, 100 - initial.y); next.x = newX; break;
      }
      case "resize-se":
        next.w = clamp(initial.w + dxPct, 5, 100 - initial.x);
        next.h = clamp(initial.h + dyPct, 5, 100 - initial.y); break;
    }
    onCropChange(formatCrop(next));
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (dragMode === "none") return;
    setDragMode("none");
    try { (e.target as HTMLElement).releasePointerCapture(e.pointerId); } catch {}
    dragStartRef.current = null;
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <p className="text-sm font-medium flex items-center gap-2 text-slate-700">
          <Crop className="h-4 w-4" /> Recorte da imagem (crop)
        </p>
        {cropEnabled ? (
          <Button variant="outline" size="sm" onClick={handleDisable} className="text-red-600 border-red-200 hover:bg-red-50">
            <X className="h-4 w-4" /> Remover recorte
          </Button>
        ) : (
          <Button variant="outline" size="sm" onClick={handleEnable}>
            <Crop className="h-4 w-4" /> Activar recorte
          </Button>
        )}
      </div>

      <div
        ref={canvasRef}
        className="relative w-full bg-slate-900 rounded-lg overflow-hidden select-none"
        style={{ aspectRatio: "16/9" }}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {snapshotUrl ? (
          <img src={snapshotUrl} alt="Câmara" className="absolute inset-0 w-full h-full object-contain pointer-events-none" draggable={false} />
        ) : snapshotError ? (
          <div className="absolute inset-0 flex items-center justify-center text-red-400 text-sm px-4 text-center">
            <div><ImageOff className="h-8 w-8 mx-auto mb-2" />{snapshotError}</div>
          </div>
        ) : isLoadingSnapshot ? (
          <div className="absolute inset-0 flex items-center justify-center text-white"><Loader2 className="h-8 w-8 animate-spin" /></div>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-sm">Sem imagem</div>
        )}

        {current && (
          <>
            <div className="absolute bg-black/50 pointer-events-none" style={{ left: 0, top: 0, right: 0, height: `${current.y}%` }} />
            <div className="absolute bg-black/50 pointer-events-none" style={{ left: 0, top: `${current.y + current.h}%`, right: 0, bottom: 0 }} />
            <div className="absolute bg-black/50 pointer-events-none" style={{ left: 0, top: `${current.y}%`, width: `${current.x}%`, height: `${current.h}%` }} />
            <div className="absolute bg-black/50 pointer-events-none" style={{ left: `${current.x + current.w}%`, top: `${current.y}%`, right: 0, height: `${current.h}%` }} />
            <div
              className="absolute border-2 border-yellow-400"
              style={{ left: `${current.x}%`, top: `${current.y}%`, width: `${current.w}%`, height: `${current.h}%`,
                cursor: dragMode === "move" ? "grabbing" : "grab", touchAction: "none" }}
              onPointerDown={(e) => startDrag("move", e)}
            >
              <CornerHandle position="nw" onPointerDown={(e) => startDrag("resize-nw", e)} />
              <CornerHandle position="ne" onPointerDown={(e) => startDrag("resize-ne", e)} />
              <CornerHandle position="sw" onPointerDown={(e) => startDrag("resize-sw", e)} />
              <CornerHandle position="se" onPointerDown={(e) => startDrag("resize-se", e)} />
            </div>
          </>
        )}
      </div>

      {cropEnabled && current && (
        <p className="text-xs text-slate-500">
          Recorte: <code>X={current.x.toFixed(0)}% Y={current.y.toFixed(0)}% W={current.w.toFixed(0)}% H={current.h.toFixed(0)}%</code>
          <span className="ml-2 text-slate-400">(arrasta para mover, cantos para redimensionar)</span>
        </p>
      )}
      {!cropEnabled && <p className="text-xs text-slate-500">Sem recorte — envia o frame inteiro da câmara.</p>}
    </div>
  );
};

interface CropRect { x: number; y: number; w: number; h: number; }
function parseCrop(s: string): CropRect | null {
  const p = s.split(",").map((v) => parseFloat(v));
  if (p.length !== 4 || p.some((v) => isNaN(v))) return null;
  return { x: p[0], y: p[1], w: p[2], h: p[3] };
}
function formatCrop(c: CropRect): string {
  return `${c.x.toFixed(1)},${c.y.toFixed(1)},${c.w.toFixed(1)},${c.h.toFixed(1)}`;
}
function clamp(v: number, min: number, max: number) { return Math.max(min, Math.min(v, max)); }

const CornerHandle: React.FC<{ position: "nw" | "ne" | "sw" | "se"; onPointerDown: (e: React.PointerEvent) => void; }> = ({ position, onPointerDown }) => {
  const cursors: Record<string, string> = { nw: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize", se: "nwse-resize" };
  const positions: Record<string, React.CSSProperties> = {
    nw: { left: -8, top: -8 }, ne: { right: -8, top: -8 }, sw: { left: -8, bottom: -8 }, se: { right: -8, bottom: -8 },
  };
  return (
    <div onPointerDown={onPointerDown} className="absolute w-4 h-4 bg-yellow-400 border-2 border-white rounded-sm shadow"
      style={{ ...positions[position], cursor: cursors[position], touchAction: "none" }} />
  );
};
