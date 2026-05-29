import React from "react";

export function cn(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "danger" | "outline" | "ghost" | "stop";
  size?: "sm" | "md";
};

export const Button: React.FC<BtnProps> = ({
  variant = "primary",
  size = "md",
  className,
  children,
  ...rest
}) => {
  const base =
    "inline-flex items-center justify-center gap-2 font-semibold rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed";
  const sizes = size === "sm" ? "text-xs px-3 py-1.5" : "text-sm px-4 py-2.5";
  const variants: Record<string, string> = {
    primary: "bg-blue-600 hover:bg-blue-700 text-white",
    danger: "bg-red-600 hover:bg-red-700 text-white",
    stop: "bg-slate-600 hover:bg-slate-700 text-white",
    outline: "bg-white border border-slate-300 text-slate-700 hover:border-blue-500 hover:text-blue-600",
    ghost: "bg-transparent text-slate-600 hover:bg-slate-100",
  };
  return (
    <button className={cn(base, sizes, variants[variant], className)} {...rest}>
      {children}
    </button>
  );
};
