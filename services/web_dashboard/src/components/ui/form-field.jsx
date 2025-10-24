import React from "react";
import { cn } from "../../lib/utils.js";

export function Form({ className, ...props }) {
  return <form className={cn("flex flex-col gap-6", className)} {...props} />;
}

export function FormField({ className, ...props }) {
  return <div className={cn("flex flex-col gap-2", className)} {...props} />;
}

export function FormLabel({ className, ...props }) {
  return <label className={cn("text-sm font-medium text-slate-300", className)} {...props} />;
}

export function FormControl({ className, ...props }) {
  return <div className={cn("flex flex-col gap-2", className)} {...props} />;
}

export function FormDescription({ className, ...props }) {
  return <p className={cn("text-xs text-slate-400", className)} {...props} />;
}

const MESSAGE_VARIANTS = {
  default: "text-xs text-slate-300",
  success: "text-xs text-emerald-300",
  warning: "text-xs text-amber-300",
  error: "text-xs text-rose-300",
};

export function FormMessage({ className, variant = "default", ...props }) {
  return <p className={cn(MESSAGE_VARIANTS[variant] || MESSAGE_VARIANTS.default, className)} {...props} />;
}
