import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import path from "node:path";

// `npm run build:static` makes one self-contained HTML file with a data snapshot inside (no server needed).
const STATIC = process.env.VITE_STATIC === "1";

export default defineConfig({
  plugins: [react(), tailwindcss(), ...(STATIC ? [viteSingleFile()] : [])],
  resolve: {
    alias: { "snapshot-data": path.resolve(__dirname, STATIC ? "static-snapshot.json" : "src/snapshot-stub.json") },
  },
  server: { proxy: { "/api": "http://localhost:8000" } },
});
