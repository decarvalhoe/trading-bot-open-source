import React, { forwardRef } from "react";
import { cn } from "../../lib/utils.js";

const BASE_INPUT_CLASSES =
  "flex h-11 w-full items-center rounded-xl border border-slate-800/70 bg-slate-900/60 px-4 text-sm text-slate-100 shadow-inner shadow-slate-950/40 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 placeholder:text-slate-500 disabled:cursor-not-allowed disabled:opacity-60";

export const Input = forwardRef(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn(BASE_INPUT_CLASSES, className)} {...props} />;
});

export const Textarea = forwardRef(function Textarea({ className, rows = 3, ...props }, ref) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      className={cn(
        BASE_INPUT_CLASSES,
        "min-h-[2.75rem] resize-y py-3 leading-relaxed",
        className,
      )}
      {...props}
    />
  );
});
