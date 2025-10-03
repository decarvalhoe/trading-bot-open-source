import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "app/static/dist",
    emptyOutDir: false,
    assetsDir: ".",
    rollupOptions: {
      input: {
        dashboard: "src/main.jsx",
        account: "src/account/main.jsx"
      },
      output: {
        entryFileNames: (chunkInfo) => {
          if (chunkInfo.name === "dashboard") {
            return "portfolio-chart.js";
          }
          if (chunkInfo.name === "account") {
            return "account-app.js";
          }
          return "[name].js";
        },
        chunkFileNames: "[name].[hash].js",
        assetFileNames: "[name].[hash][extname]"
      }
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./test/setup.js"],
    css: false,
    globals: true
  }
});
