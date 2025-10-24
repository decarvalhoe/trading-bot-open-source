import React, { forwardRef } from "react";
import { cn } from "../../lib/utils.js";

const VARIANTS = {
  primary: "bg-sky-500/90 text-slate-950 shadow-lg shadow-sky-900/50 hover:bg-sky-400",
  secondary: "border border-slate-700 bg-slate-900/70 text-slate-100 shadow shadow-slate-950/40 hover:border-slate-500 hover:text-white",
  outline: "border border-slate-700 bg-transparent text-slate-200 hover:border-slate-500 hover:text-white",
  ghost: "bg-transparent text-slate-300 hover:bg-slate-800/60 hover:text-white",
  destructive: "bg-rose-500/90 text-white shadow-lg shadow-rose-900/40 hover:bg-rose-400",
  success: "bg-emerald-500/90 text-slate-950 shadow-lg shadow-emerald-900/40 hover:bg-emerald-400",
};

const SIZES = {
  sm: "h-9 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-base",
  icon: "h-10 w-10 p-0",
};

export const Button = forwardRef(function Button(
  { className, variant = "secondary", size = "md", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 disabled:cursor-not-allowed disabled:opacity-60",
        VARIANTS[variant] || VARIANTS.secondary,
        SIZES[size] || SIZES.md,
        className,
      )}
      {...props}
    />
  );
});
