import React from "react";
import { cn } from "../../lib/utils.js";

const VARIANTS = {
  neutral: "bg-slate-800/80 text-slate-200 ring-1 ring-inset ring-slate-700/60",
  info: "bg-sky-500/15 text-sky-200 ring-1 ring-inset ring-sky-400/40",
  success: "bg-emerald-500/15 text-emerald-200 ring-1 ring-inset ring-emerald-400/40",
  warning: "bg-amber-500/15 text-amber-200 ring-1 ring-inset ring-amber-400/40",
  critical: "bg-rose-500/15 text-rose-200 ring-1 ring-inset ring-rose-400/40",
};

export function Badge({ className, variant = "neutral", ...props }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide",
        VARIANTS[variant] || VARIANTS.neutral,
        className,
      )}
      {...props}
    />
  );
}
