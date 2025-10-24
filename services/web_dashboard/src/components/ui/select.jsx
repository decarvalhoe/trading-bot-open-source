import React, { forwardRef } from "react";
import { cn } from "../../lib/utils.js";

const BASE_SELECT_CLASSES =
  "flex h-11 w-full items-center rounded-xl border border-slate-800/70 bg-slate-900/60 px-4 text-sm text-slate-100 shadow-inner shadow-slate-950/40 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 appearance-none disabled:cursor-not-allowed disabled:opacity-60";

export const Select = forwardRef(function Select({ className, children, ...props }, ref) {
  return (
    <div className="relative w-full">
      <select ref={ref} className={cn(BASE_SELECT_CLASSES, "pr-10", className)} {...props}>
        {children}
      </select>
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
      >
        <path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </div>
  );
});
