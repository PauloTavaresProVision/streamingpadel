import React, { useEffect, useRef, useState } from "react";

interface Props {
  text?: string | null;
  showClock: boolean;
  position: string;            // TopLeft|TopCenter|TopRight|BottomLeft|BottomCenter|BottomRight
  fontSize: number;            // px relativos a output 1080p
  fontColor: string;           // #rrggbb ou nome
  fontFamily: string;
  bold?: boolean;
  italic?: boolean;
  bg?: boolean;                // fundo sombreado
  /** largura de referência do output (default 1920) para escalar a fonte ao preview. */
  outputWidth?: number;
}

export const FAMILY: Record<string, string> = {
  "Sans": "system-ui, sans-serif",
  "Serif": "Georgia, 'Times New Roman', serif",
  "Monospace": "'Courier New', monospace",
  "DejaVu Sans": "'DejaVu Sans', system-ui, sans-serif",
  "DejaVu Serif": "'DejaVu Serif', Georgia, serif",
  "Liberation Sans": "'Liberation Sans', Arial, sans-serif",
  "Noto Sans": "'Noto Sans', system-ui, sans-serif",
  "Impact": "Impact, 'Arial Black', sans-serif",
};

/**
 * Desenha texto fixo + relógio sobre o preview, exactamente na posição/cor/fonte
 * configuradas. A fonte é escalada à largura real do preview para corresponder
 * ao que o GStreamer vai produzir no output. Não-interactivo (pointer-events:none).
 */
export const OverlayText: React.FC<Props> = ({
  text, showClock, position, fontSize, fontColor, fontFamily,
  bold, italic, bg = true, outputWidth = 1920,
}) => {
  const ref = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.5);
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    if (!showClock) return;
    const i = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(i);
  }, [showClock]);

  useEffect(() => {
    const el = ref.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver(() => setScale(el.clientWidth / outputWidth));
    ro.observe(el);
    setScale(el.clientWidth / outputWidth);
    return () => ro.disconnect();
  }, [outputWidth]);

  const hasText = !!(text && text.trim());
  if (!hasText && !showClock) return null;

  const px = Math.max(6, fontSize * scale);
  const pos = posStyle(position);
  const clock = now.toLocaleTimeString("pt-PT", { hour12: false });

  const chip: React.CSSProperties = {
    background: bg ? "rgba(0,0,0,0.5)" : "transparent",
    color: fontColor, padding: bg ? `${px * 0.2}px ${px * 0.35}px` : 0,
    borderRadius: 3, fontSize: px, fontFamily: FAMILY[fontFamily] || FAMILY.Sans,
    fontWeight: bold ? 700 : 400, fontStyle: italic ? "italic" : "normal",
    lineHeight: 1.2, whiteSpace: "pre", display: "inline-block",
    textShadow: bg ? "none" : "0 1px 3px rgba(0,0,0,0.9)",
  };

  return (
    <div ref={ref} className="absolute inset-0 pointer-events-none">
      <div className="absolute flex flex-col gap-1" style={pos}>
        {hasText && <span style={chip}>{text}</span>}
        {showClock && <span style={chip}>{clock}</span>}
      </div>
    </div>
  );
};

function posStyle(position: string): React.CSSProperties {
  const m = "3%";
  const base: React.CSSProperties = { textAlign: position.includes("Center") ? "center" : position.includes("Right") ? "right" : "left" };
  switch (position) {
    case "TopLeft": return { ...base, top: m, left: m };
    case "TopCenter": return { ...base, top: m, left: "50%", transform: "translateX(-50%)" };
    case "TopRight": return { ...base, top: m, right: m, alignItems: "flex-end" };
    case "BottomCenter": return { ...base, bottom: m, left: "50%", transform: "translateX(-50%)" };
    case "BottomRight": return { ...base, bottom: m, right: m, alignItems: "flex-end" };
    case "BottomLeft": default: return { ...base, bottom: m, left: m };
  }
}
