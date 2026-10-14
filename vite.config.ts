import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

const apiProxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000';

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      proxy: {'/api': apiProxyTarget},
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modify—file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Disable file watching when DISABLE_HMR is true to save CPU during agent edits.
      watch: process.env.DISABLE_HMR === 'true' ? null : {
        // Backend/evidence writes must not reload the browser and discard a
        // memory-only login or unsent microphone audio.
        ignored: ['**/backend/**', '**/e2e_validation/**', '**/docs/**',
          '**/data/**', '**/notebooks/**', '**/.venv/**', '**/.runtime/**', '**/*.md'],
      },
    },
  };
});
