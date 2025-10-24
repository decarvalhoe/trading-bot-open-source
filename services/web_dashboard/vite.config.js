import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "app/static/dist",
    emptyOutDir: false,
    assetsDir: "assets",
    cssCodeSplit: false,
    rollupOptions: {
      input: {
        app: "src/main.jsx"
      },
      output: {
        entryFileNames: () => "app.js",
        chunkFileNames: "[name].[hash].js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".css")) {
            return "assets/index.css";
          }
          return "assets/[name].[hash][extname]";
        }
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
