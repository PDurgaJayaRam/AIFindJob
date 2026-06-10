import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server proxies API calls to the FastAPI backend so the frontend can call
// /ingestion/* and /auth/* without CORS or hardcoded hosts.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/ingestion': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/me': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/resume': 'http://localhost:8000',
      '/live-scraper': 'http://localhost:8000',
    },
  },
});
