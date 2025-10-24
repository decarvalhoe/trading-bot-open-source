import defaultTheme from "tailwindcss/defaultTheme";
import forms from "@tailwindcss/forms";

export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}", "./app/templates/**/*.html"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", ...defaultTheme.fontFamily.sans],
      },
      colors: {
        background: {
          DEFAULT: "#0f172a",
          subtle: "#111c3b",
          muted: "rgba(15, 23, 42, 0.45)",
        },
        foreground: "#f8fafc",
        muted: "#94a3b8",
        success: "#22c55e",
        warning: "#f97316",
        critical: "#ef4444",
        info: "#38bdf8",
      },
      boxShadow: {
        glow: "0 12px 30px rgba(15, 23, 42, 0.35)",
      },
      borderRadius: {
        xl: "12px",
        lg: "0.75rem",
      },
      backgroundImage: {
        "dashboard-radial":
          "radial-gradient(circle at top, rgba(56, 189, 248, 0.1), transparent 60%), radial-gradient(circle at bottom, rgba(99, 102, 241, 0.07), transparent 55%)",
      },
    },
  },
  plugins: [forms],
};
