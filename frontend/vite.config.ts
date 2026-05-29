import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build para ../app/webdist; o FastAPI serve index.html em / e /assets estático.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "../app/webdist",
    emptyOutDir: true,
  },
  server: {
    // dev: proxy /api e /data para o uvicorn local
    proxy: {
      "/api": "http://localhost:8000",
      "/data": "http://localhost:8000",
    },
  },
});
