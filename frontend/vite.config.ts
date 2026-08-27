import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/metrics": "http://127.0.0.1:8000",
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;

          if (
            id.includes("/react-markdown/") ||
            id.includes("/remark-") ||
            id.includes("/rehype-") ||
            id.includes("/highlight.js/") ||
            id.includes("/lowlight/") ||
            id.includes("/unified/") ||
            id.includes("/micromark") ||
            id.includes("/mdast-") ||
            id.includes("/hast-") ||
            id.includes("/property-information/") ||
            id.includes("/vfile")
          ) {
            return "markdown";
          }

          if (
            id.includes("/radix-ui/") ||
            id.includes("/lucide-react/") ||
            id.includes("/sonner/") ||
            id.includes("/next-themes/") ||
            id.includes("/tw-animate-css/") ||
            id.includes("/class-variance-authority/") ||
            id.includes("/tailwind-merge/") ||
            id.includes("/clsx/")
          ) {
            return "ui-vendor";
          }

          return "vendor";
        },
      },
    },
  },
});
