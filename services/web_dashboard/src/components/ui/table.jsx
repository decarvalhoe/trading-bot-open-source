import React from "react";
import { cn } from "../../lib/utils.js";

export function Table({ className, ...props }) {
  return <div className={cn("overflow-hidden rounded-2xl border border-slate-800/60", className)} {...props} />;
}

export function TableContent({ className, ...props }) {
  return <div className={cn("overflow-x-auto", className)} {...props} />;
}

export function TableElement({ className, ...props }) {
  return (
    <table
      className={cn(
        "min-w-full border-collapse bg-slate-900/70 text-left text-sm text-slate-200 shadow-2xl shadow-slate-950/40",
        className,
      )}
      {...props}
    />
  );
}

export function TableHeader({ className, ...props }) {
  return <thead className={cn("bg-slate-900/80 text-xs uppercase text-slate-400", className)} {...props} />;
}

export function TableBody({ className, ...props }) {
  return <tbody className={cn("divide-y divide-slate-800/60", className)} {...props} />;
}

export function TableRow({ className, ...props }) {
  return (
    <tr
      className={cn(
        "transition hover:bg-slate-800/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/70",
        className,
      )}
      {...props}
    />
  );
}

export function TableHead({ className, ...props }) {
  return <th className={cn("px-5 py-3 font-semibold tracking-wide", className)} scope="col" {...props} />;
}

export function TableCell({ className, ...props }) {
  return <td className={cn("px-5 py-4 align-middle text-slate-200", className)} {...props} />;
}

export function TableCaption({ className, ...props }) {
  return <caption className={cn("px-5 py-3 text-left text-xs text-slate-500", className)} {...props} />;
}
