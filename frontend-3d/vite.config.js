import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/ingestion': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/me': 'http://localhost:8000',
      '/resume': 'http://localhost:8000',
      '/live-scraper': 'http://localhost:8000',
      '/chat': 'http://localhost:8000',
      '/company-research': 'http://localhost:8000',
      '/find-people': 'http://localhost:8000',
      '/scheduler': 'http://localhost:8000',
      '/admin/overview': 'http://localhost:8000',
      '/admin/events': 'http://localhost:8000',
      '/admin/portals': 'http://localhost:8000',
      '/admin/scrape': 'http://localhost:8000',
      '/admin/trigger': 'http://localhost:8000',
      '/admin/login': 'http://localhost:8000',
    },
  },
});
