import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// 开发期把 /api 转发到本地后端，浏览器看到的是同源请求，不需要跨域。
// 后端地址用 VITE_DEV_PROXY_TARGET 配置（见 .env.example），默认是待确认的 http://127.0.0.1:8000。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000';

  return {
    // 相对路径：部署到任意子路径都能用（路由用的是 hash，不受影响）
    base: './',
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: true },
      },
      fs: {
        // 前端模拟适配器只读引用 contracts/examples 里的正式示例 JSON。
        allow: ['.', '../contracts/examples'],
      },
    },
    preview: {
      port: 4173,
      strictPort: true,
      proxy: {
        '/api': { target: proxyTarget, changeOrigin: true },
      },
    },
  };
});
