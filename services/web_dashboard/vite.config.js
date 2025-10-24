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
        app: "src/main.jsx"
      },
      output: {
        entryFileNames: () => "app.js",
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
