import React from "react";
import { cn } from "../../lib/utils.js";

export function Card({ as: Component = "section", className, ...props }) {
  return (
    <Component
      className={cn(
        "group flex min-h-full flex-col overflow-hidden rounded-3xl border border-slate-800/60 bg-slate-900/70 shadow-2xl shadow-slate-950/40 backdrop-blur",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }) {
  return (
    <div
      className={cn(
        "border-b border-slate-800/60 px-6 pb-4 pt-6",
        className,
      )}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }) {
  return <h2 className={cn("text-2xl font-semibold text-white", className)} {...props} />;
}

export function CardDescription({ className, ...props }) {
  return <p className={cn("mt-2 text-sm text-slate-400", className)} {...props} />;
}

export function CardContent({ className, ...props }) {
  return <div className={cn("flex flex-col gap-4 px-6 py-6 text-sm", className)} {...props} />;
}

export function CardFooter({ className, ...props }) {
  return <div className={cn("border-t border-slate-800/60 px-6 py-4", className)} {...props} />;
}
