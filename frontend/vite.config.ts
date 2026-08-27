import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const target = process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000'
const proxy = {
  '/api': { target, changeOrigin: true, rewrite: (path: string) => path.replace(/^\/api/, '') },
  '/docs': { target, changeOrigin: true },
  '/openapi.json': { target, changeOrigin: true },
}

export default defineConfig({
  plugins: [react()],
  server: { proxy, strictPort: true },
  preview: { proxy, strictPort: true },
})
