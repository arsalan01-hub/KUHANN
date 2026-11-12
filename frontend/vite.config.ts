import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const previewHost = process.env.BASE44_PUBLIC_HOST_SUFFIX
  ? `3000-${process.env.BASE44_PUBLIC_HOST_SUFFIX}`
  : undefined;

// The Base44 sandbox proxy forwards a rotating host, so allow the current
// preview host plus any sibling *.sandbox host when the platform asks for it.
const allowedHosts = previewHost ? [previewHost] : [];

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
    watch: { usePolling: true, interval: 400 },
  },
  build: { outDir: 'dist', sourcemap: false },
});
