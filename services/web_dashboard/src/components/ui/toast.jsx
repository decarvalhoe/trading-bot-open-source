import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "../../lib/utils.js";

const ToastContext = createContext(null);
let toastCounter = 0;

const VARIANTS = {
  default: "border-slate-700 bg-slate-900/90 text-slate-100",
  success: "border-emerald-500/50 bg-emerald-500/15 text-emerald-200",
  warning: "border-amber-500/50 bg-amber-500/15 text-amber-200",
  danger: "border-rose-500/50 bg-rose-500/15 text-rose-200",
  info: "border-sky-500/50 bg-sky-500/15 text-sky-200",
};

export function ToastProvider({ children, duration = 4000, placement = "bottom-right" }) {
  const [toasts, setToasts] = useState([]);
  const timeoutsRef = useRef(new Map());

  const clearExistingTimeout = useCallback((id) => {
    const timeoutId = timeoutsRef.current.get(id);
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutsRef.current.delete(id);
    }
  }, []);

  const dismiss = useCallback(
    (id) => {
      clearExistingTimeout(id);
      setToasts((previous) => previous.filter((toast) => toast.id !== id));
    },
    [clearExistingTimeout],
  );

  const show = useCallback(
    ({ title, description, variant = "default", actionLabel, onAction, duration: toastDuration }) => {
      const id = `toast-${toastCounter++}`;
      setToasts((previous) => [...previous, { id, title, description, variant, actionLabel, onAction }]);
      const timeoutDelay = toastDuration ?? duration;
      if (timeoutDelay > 0) {
        const timeout = setTimeout(() => {
          dismiss(id);
        }, timeoutDelay);
        timeoutsRef.current.set(id, timeout);
      }
      return id;
    },
    [dismiss, duration],
  );

  useEffect(() => {
    return () => {
      timeoutsRef.current.forEach((timeoutId) => clearTimeout(timeoutId));
      timeoutsRef.current.clear();
    };
  }, []);

  const contextValue = useMemo(
    () => ({
      show,
      dismiss,
      toasts,
    }),
    [show, dismiss, toasts],
  );

  return (
    <ToastContext.Provider value={contextValue}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} placement={placement} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used inside a <ToastProvider>");
  }
  return context;
}

function ToastViewport({ toasts, onDismiss, placement }) {
  if (toasts.length === 0) {
    return null;
  }

  const placementClass = {
    "bottom-right": "bottom-6 right-6 items-end",
    "bottom-left": "bottom-6 left-6 items-start",
    "top-right": "top-6 right-6 items-end",
    "top-left": "top-6 left-6 items-start",
  }[placement];

  return createPortal(
    <div className={cn("pointer-events-none fixed z-[60] flex w-full max-w-sm flex-col gap-3", placementClass)}>
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>,
    document.body,
  );
}

function ToastItem({ toast, onDismiss }) {
  const handleDismiss = useCallback(() => {
    onDismiss(toast.id);
  }, [onDismiss, toast.id]);

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "pointer-events-auto flex flex-col gap-2 rounded-2xl border px-4 py-3 shadow-lg shadow-slate-950/40 backdrop-blur",
        VARIANTS[toast.variant] || VARIANTS.default,
      )}
    >
      {toast.title && <p className="text-sm font-semibold text-white">{toast.title}</p>}
      {toast.description && <p className="text-sm text-slate-200">{toast.description}</p>}
      {(toast.actionLabel || toast.onAction) && (
        <div className="flex items-center gap-2">
          {toast.actionLabel && (
            <button
              type="button"
              className="rounded-lg bg-slate-800/60 px-3 py-1 text-xs font-medium text-slate-200 transition hover:bg-slate-800"
              onClick={() => {
                toast.onAction?.();
                handleDismiss();
              }}
            >
              {toast.actionLabel}
            </button>
          )}
          <button
            type="button"
            onClick={handleDismiss}
            className="ml-auto text-xs uppercase tracking-wide text-slate-400 transition hover:text-slate-100"
          >
            Fermer
          </button>
        </div>
      )}
      {!toast.actionLabel && !toast.onAction && (
        <button
          type="button"
          onClick={handleDismiss}
          className="self-end text-xs uppercase tracking-wide text-slate-400 transition hover:text-slate-100"
        >
          Fermer
        </button>
      )}
    </div>
  );
}
