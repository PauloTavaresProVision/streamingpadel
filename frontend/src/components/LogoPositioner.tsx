import React, { useMemo, useRef, useState } from "react";
import { Button } from "../ui";
import { Loader2, RefreshCw, ImageOff } from "lucide-react";

interface LogoPositionerProps {
  snapshotUrl: string | null;
  isLoadingSnapshot: boolean;
  snapshotError: string | null;
  logoUrl: string | null;
  logoSizePercent: number;
  logoOpacity: number;
  position: string;
  cropRegion?: string;
  /** Camada extra (ex: texto/hora) renderizada dentro do canvas, por cima da imagem. */
  overlay?: React.ReactNode;
  onPositionChange: (newPosition: string) => void;
  onSizeChange: (newSizePercent: number) => void;
  onRefresh: () => void;
}

type DragMode = "none" | "move" | "resize";

export const LogoPositioner: React.FC<LogoPositionerProps> = ({
  snapshotUrl, isLoadingSnapshot, snapshotError, logoUrl,
  logoSizePercent, logoOpacity, position, cropRegion, overlay,
  onPositionChange, onSizeChange, onRefresh,
}) => {
  const cropStyles = useCropStyles(cropRegion);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [dragMode, setDragMode] = useState<DragMode>("none");
  const [naturalLogoSize, setNaturalLogoSize] = useState({ w: 0, h: 0 });
  const currentXY = parsePositionToPercent(position);

  const handleMoveDown = (e: React.PointerEvent) => {
    if (!canvasRef.current || !logoUrl) return;
    e.preventDefault(); e.stopPropagation();
    setDragMode("move");
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    movePointer(e.clientX, e.clientY);
  };
  const handleResizeDown = (e: React.PointerEvent) => {
    if (!canvasRef.current || !logoUrl) return;
    e.preventDefault(); e.stopPropagation();
    setDragMode("resize");
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    resizePointer(e.clientX);
  };
  const handlePointerMove = (e: React.PointerEvent) => {
    if (dragMode === "move") movePointer(e.clientX, e.clientY);
    else if (dragMode === "resize") resizePointer(e.clientX);
  };
  const handlePointerUp = (e: React.PointerEvent) => {
    if (dragMode === "none") return;
    setDragMode("none");
    try { (e.target as HTMLElement).releasePointerCapture(e.pointerId); } catch {}
  };

  const movePointer = (clientX: number, clientY: number) => {
    const canvas = canvasRef.current; if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    let x = clientX - rect.left, y = clientY - rect.top;
    const logoW = (logoSizePercent / 100) * rect.width;
    const logoH = naturalLogoSize.w > 0 ? logoW * (naturalLogoSize.h / naturalLogoSize.w) : logoW;
    x -= logoW / 2; y -= logoH / 2;
    x = Math.max(0, Math.min(x, rect.width - logoW));
    y = Math.max(0, Math.min(y, rect.height - logoH));
    onPositionChange(`${((x / rect.width) * 100).toFixed(1)},${((y / rect.height) * 100).toFixed(1)}`);
  };
  const resizePointer = (clientX: number) => {
    const canvas = canvasRef.current; if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const leftOfLogoPx = (currentXY.x / 100) * rect.width;
    const newWidthPx = Math.max(20, (clientX - rect.left) - leftOfLogoPx);
    let newSizePct = (newWidthPx / rect.width) * 100;
    newSizePct = Math.max(5, Math.min(30, newSizePct));
    const maxAllowed = 100 - currentXY.x - 0.5;
    if (maxAllowed > 5) newSizePct = Math.min(newSizePct, maxAllowed);
    onSizeChange(Math.round(newSizePct));
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-slate-700">Pré-visualização — arrasta o logo</p>
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={isLoadingSnapshot}>
          {isLoadingSnapshot ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Actualizar imagem
        </Button>
      </div>

      <div ref={canvasRef}
        className="relative w-full bg-slate-900 rounded-lg overflow-hidden select-none"
        style={{ aspectRatio: "16/9" }}
        onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp}>
        {snapshotUrl ? (
          <img src={snapshotUrl} alt="Câmara" className="absolute pointer-events-none" draggable={false}
            style={cropStyles ?? { left: 0, top: 0, width: "100%", height: "100%", objectFit: "contain" }} />
        ) : snapshotError ? (
          <div className="absolute inset-0 flex items-center justify-center text-red-400 text-sm px-4 text-center">
            <div><ImageOff className="h-8 w-8 mx-auto mb-2" />{snapshotError}</div>
          </div>
        ) : isLoadingSnapshot ? (
          <div className="absolute inset-0 flex items-center justify-center text-white">
            <div className="text-center"><Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" /><p className="text-xs">A capturar imagem...</p></div>
          </div>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-sm">Sem imagem</div>
        )}

        {/* Camada de texto/hora (não-interactiva) */}
        {overlay}

        {logoUrl && (
          <div className="absolute group" style={{ left: `${currentXY.x}%`, top: `${currentXY.y}%`, width: `${logoSizePercent}%`, opacity: logoOpacity / 100, touchAction: "none" }}>
            <img src={logoUrl} alt="Logo" draggable={false}
              onLoad={(e) => { const img = e.currentTarget; setNaturalLogoSize({ w: img.naturalWidth, h: img.naturalHeight }); }}
              onPointerDown={handleMoveDown} className="block w-full h-auto"
              style={{ cursor: dragMode === "move" ? "grabbing" : "grab", filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.4))", userSelect: "none" }} />
            <div className={`absolute inset-0 pointer-events-none border-2 border-dashed transition-opacity ${dragMode !== "none" ? "border-blue-400 opacity-100" : "border-blue-400 opacity-0 group-hover:opacity-60"}`} />
            <div onPointerDown={handleResizeDown} title="Redimensionar"
              className={`absolute -right-2 -bottom-2 w-5 h-5 bg-blue-500 border-2 border-white rounded-full shadow-md transition-opacity ${dragMode === "resize" ? "opacity-100 scale-110" : "opacity-0 group-hover:opacity-100"}`}
              style={{ cursor: "nwse-resize", touchAction: "none" }} />
          </div>
        )}
      </div>

      <p className="text-xs text-slate-500">
        Posição: <code>{position}</code>{position.includes(",") && " (custom)"} · Tamanho: <code>{logoSizePercent}%</code>
        {cropStyles && <span className="ml-2 text-blue-600 font-medium">Preview mostra apenas a região cortada</span>}
      </p>
    </div>
  );
};

function useCropStyles(cropRegion: string | undefined): React.CSSProperties | null {
  return useMemo(() => {
    if (!cropRegion) return null;
    const p = cropRegion.split(",").map((v) => parseFloat(v));
    if (p.length !== 4 || p.some((v) => isNaN(v))) return null;
    const [x, y, w, h] = p;
    if (w <= 0 || h <= 0) return null;
    if (x === 0 && y === 0 && w >= 99.5 && h >= 99.5) return null;
    return {
      left: `-${((x * 100) / w).toFixed(2)}%`, top: `-${((y * 100) / h).toFixed(2)}%`,
      width: `${((100 * 100) / w).toFixed(2)}%`, height: `${((100 * 100) / h).toFixed(2)}%`,
      objectFit: "fill" as const, maxWidth: "none", maxHeight: "none",
    };
  }, [cropRegion]);
}

function parsePositionToPercent(position: string): { x: number; y: number } {
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
