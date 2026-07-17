import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// O backend (FastAPI) roda na porta 8756. O Vite (dev) roda na 5173 e
// redireciona as chamadas de API/midia para o backend.
const backend = 'http://127.0.0.1:8756'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': backend,
      '/media': backend,
      '/output': backend,
    },
  },
  build: { outDir: 'dist' },
})
