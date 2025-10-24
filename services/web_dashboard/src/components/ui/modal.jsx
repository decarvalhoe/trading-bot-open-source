import React, { createContext, forwardRef, useCallback, useContext, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { cn } from "../../lib/utils.js";

const ModalContext = createContext(null);

const SIZES = {
  sm: "max-w-md",
  md: "max-w-2xl",
  lg: "max-w-4xl",
};

export function Modal({ open, onClose, size = "md", className, children, labelledBy, description }) {
  const handleKeyDown = useCallback(
    (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose?.();
      }
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, handleKeyDown]);

  const value = useMemo(
    () => ({ onClose }),
    [onClose],
  );

  if (!open) {
    return null;
  }

  return createPortal(
    <ModalContext.Provider value={value}>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm"
          aria-hidden="true"
          data-testid="modal-overlay"
          onClick={() => onClose?.()}
        />
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby={labelledBy}
          aria-describedby={description}
          className={cn(
            "relative z-10 flex w-full flex-col gap-4 rounded-3xl border border-slate-800/70 bg-slate-900/80 p-6 text-slate-100 shadow-2xl shadow-slate-950/60",
            SIZES[size] || SIZES.md,
            className,
          )}
        >
          {children}
        </div>
      </div>
    </ModalContext.Provider>,
    document.body,
  );
}

export function ModalHeader({ className, ...props }) {
  return <header className={cn("flex flex-col gap-1", className)} {...props} />;
}

export function ModalTitle({ className, ...props }) {
  return <h2 className={cn("text-2xl font-semibold text-white", className)} {...props} />;
}

export function ModalDescription({ className, ...props }) {
  return <p className={cn("text-sm text-slate-400", className)} {...props} />;
}

export function ModalBody({ className, ...props }) {
  return <div className={cn("flex flex-col gap-4", className)} {...props} />;
}

export function ModalFooter({ className, children, ...props }) {
  const context = useContext(ModalContext);

  const enhancedChildren = useMemo(() => {
    if (typeof context?.onClose !== "function") {
      return children;
    }

    return React.Children.map(children, (child) => {
      if (!React.isValidElement(child)) {
        return child;
      }
      if (child.props?.["data-modal-dismiss"]) {
        return React.cloneElement(child, {
          onClick: (event) => {
            child.props?.onClick?.(event);
            context.onClose();
          },
        });
      }
      return child;
    });
  }, [children, context]);

  return (
    <footer className={cn("flex flex-wrap items-center justify-end gap-3 pt-2", className)} {...props}>
      {enhancedChildren}
    </footer>
  );
}

export const ModalClose = forwardRef(function ModalClose({ asChild = false, onClick, className, children, ...props }, ref) {
  const context = useContext(ModalContext);
  const handleClick = useCallback(
    (event) => {
      onClick?.(event);
      context?.onClose?.();
    },
    [onClick, context],
  );

  if (asChild && children && React.isValidElement(children)) {
    return React.cloneElement(children, {
      ref,
      onClick: (event) => {
        children.props?.onClick?.(event);
        handleClick(event);
      },
    });
  }

  return (
    <button
      type="button"
      ref={ref}
      onClick={handleClick}
      className={cn(
        "inline-flex h-10 min-w-[2.5rem] items-center justify-center rounded-xl border border-slate-800/70 bg-transparent px-4 text-sm font-medium text-slate-300 transition hover:bg-slate-800/60 hover:text-white",
        className,
      )}
      {...props}
    />
  );
});
