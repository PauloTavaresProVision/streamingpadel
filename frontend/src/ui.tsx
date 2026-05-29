import React, { useState } from "react";
import { Play } from "lucide-react";

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/** Marca "PADEL LIVE" (turquesa) — ícone play num quadrado + wordmark. */
export const Brand: React.FC<{ compact?: boolean }> = ({ compact }) => (
  <div className="flex items-center gap-2.5">
    <span className="w-9 h-9 rounded-xl bg-gradient-to-br from-teal-400 to-cyan-500 flex items-center justify-center shadow-lg shadow-teal-500/20">
      <Play className="h-4 w-4 text-slate-900 fill-slate-900" />
    </span>
    {!compact && (
      <div className="leading-none">
        <div className="font-extrabold tracking-tight text-white text-lg">PADEL</div>
        <div className="font-semibold tracking-[0.25em] text-teal-400 text-[11px]">LIVE</div>
      </div>
    )}
  </div>
);

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "teal" | "danger" | "outline" | "ghost";
  size?: "sm" | "md";
};
export const Button: React.FC<BtnProps> = ({ variant = "primary", size = "md", className, children, ...rest }) => {
  const base = "inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition disabled:opacity-40 disabled:cursor-not-allowed";
  const sizes = size === "sm" ? "text-xs px-3 py-2" : "text-sm px-4 py-2.5";
  const variants: Record<string, string> = {
    primary: "bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-600/20",
    teal: "bg-teal-500 hover:bg-teal-400 text-slate-900 shadow-lg shadow-teal-500/20",
    danger: "bg-red-600 hover:bg-red-500 text-white",
    outline: "bg-transparent border border-slate-700 text-slate-200 hover:border-teal-500 hover:text-teal-400",
    ghost: "bg-transparent text-slate-400 hover:bg-slate-800 hover:text-slate-200",
  };
  return <button className={cn(base, sizes, variants[variant], className)} {...rest}>{children}</button>;
};

export const Card: React.FC<{ className?: string; children: React.ReactNode }> = ({ className, children }) => (
  <div className={cn("bg-slate-900/60 border border-slate-800 rounded-2xl", className)}>{children}</div>
);

export const Badge: React.FC<{ tone?: "live" | "prep" | "off" | "err"; children: React.ReactNode }> = ({ tone = "off", children }) => {
  const tones: Record<string, string> = {
    live: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    prep: "bg-blue-500/15 text-blue-400 border-blue-500/30",
    off: "bg-slate-700/40 text-slate-400 border-slate-700",
    err: "bg-red-500/15 text-red-400 border-red-500/30",
  };
  const dot: Record<string, string> = { live: "bg-emerald-400 animate-pulse", prep: "bg-blue-400", off: "bg-slate-500", err: "bg-red-400" };
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border", tones[tone])}>
      <span className={cn("w-1.5 h-1.5 rounded-full", dot[tone])} /> {children}
    </span>
  );
};

/** Mini sparkline SVG decorativo. */
export const Sparkline: React.FC<{ color?: string; seed?: number }> = ({ color = "#2dd4bf", seed = 1 }) => {
  const pts = Array.from({ length: 16 }, (_, i) => {
    const v = 50 + Math.sin(i * 0.7 + seed) * 22 + Math.cos(i * 1.3 + seed * 2) * 12;
    return `${(i / 15) * 100},${100 - v}`;
  }).join(" ");
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-10">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
};
