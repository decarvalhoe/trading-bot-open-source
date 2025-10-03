import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "app/static/dist",
    emptyOutDir: false,
    assetsDir: ".",
    rollupOptions: {
      input: "src/main.jsx",
      output: {
        entryFileNames: "portfolio-chart.js",
        chunkFileNames: "portfolio-chart.[hash].js",
        assetFileNames: "portfolio-chart.[hash][extname]"
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
