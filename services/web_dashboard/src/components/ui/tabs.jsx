import React, { createContext, useCallback, useContext, useId, useMemo, useState } from "react";
import { cn } from "../../lib/utils.js";

const TabsContext = createContext(null);

export function Tabs({ value, defaultValue, onValueChange, className, children }) {
  const [internalValue, setInternalValue] = useState(defaultValue);
  const controlled = value !== undefined;
  const activeValue = controlled ? value : internalValue;

  const setValue = useCallback(
    (nextValue) => {
      if (!controlled) {
        setInternalValue(nextValue);
      }
      onValueChange?.(nextValue);
    },
    [controlled, onValueChange],
  );

  const context = useMemo(
    () => ({ value: activeValue, setValue, controlled }),
    [activeValue, setValue, controlled],
  );

  return (
    <TabsContext.Provider value={context}>
      <div className={cn("flex flex-col gap-4", className)}>{children}</div>
    </TabsContext.Provider>
  );
}

function useTabsContext() {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error("Tabs components must be used within <Tabs>");
  }
  return context;
}

export function TabList({ className, children, ...props }) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex w-fit items-center gap-1 rounded-2xl border border-slate-800/60 bg-slate-900/70 p-1 text-sm shadow-inner shadow-slate-950/40",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function TabTrigger({ value, className, id, children, ...props }) {
  const { value: activeValue, setValue } = useTabsContext();
  const selected = activeValue === value;
  const generatedId = useId();
  const tabId = id ?? generatedId;

  const handleSelect = useCallback(
    (event) => {
      props.onClick?.(event);
      setValue(value);
    },
    [props, setValue, value],
  );

  return (
    <button
      type="button"
      role="tab"
      id={tabId}
      aria-selected={selected}
      className={cn(
        "relative inline-flex items-center justify-center rounded-xl px-4 py-2 font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
        selected
          ? "bg-sky-500/90 text-slate-900 shadow shadow-sky-900/40"
          : "text-slate-300 hover:text-white",
        className,
      )}
      onClick={handleSelect}
      {...props}
    >
      {children}
    </button>
  );
}

export function TabPanels({ className, children, ...props }) {
  return (
    <div className={cn("rounded-3xl border border-slate-800/60 bg-slate-900/70 p-6 shadow-2xl shadow-slate-950/40", className)} {...props}>
      {children}
    </div>
  );
}

export function TabPanel({ value, className, children, ...props }) {
  const { value: activeValue } = useTabsContext();
  const hidden = activeValue !== value;
  return (
    <div role="tabpanel" hidden={hidden} className={cn("flex flex-col gap-4 text-sm text-slate-200", className)} {...props}>
      {!hidden && children}
    </div>
  );
}
