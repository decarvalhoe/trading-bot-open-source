import React from "react";
import { cn } from "../../lib/utils.js";

const SIZES = {
  sm: "h-4 w-4 border-2",
  md: "h-6 w-6 border-[3px]",
  lg: "h-10 w-10 border-4",
};

export function Spinner({ size = "md", className, "aria-label": ariaLabel = "Chargement", ...props }) {
  return (
    <span
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
      className="inline-flex items-center justify-center"
    >
      <span
        className={cn(
          "inline-block animate-spin rounded-full border-slate-700 border-t-sky-400",
          SIZES[size] || SIZES.md,
          className,
        )}
        {...props}
      />
    </span>
  );
}
