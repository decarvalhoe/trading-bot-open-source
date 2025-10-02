import { useId, useState } from "react";

export default function Tooltip({ label, children }) {
  const tooltipId = useId();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <span
      className={`tooltip${isOpen ? " tooltip--open" : ""}`}
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
      onFocus={() => setIsOpen(true)}
      onBlur={() => setIsOpen(false)}
    >
      <button
        type="button"
        className="tooltip__trigger"
        aria-describedby={tooltipId}
      >
        {children}
      </button>
      <span role="tooltip" id={tooltipId} className="tooltip__panel">
        {label}
      </span>
    </span>
  );
}
