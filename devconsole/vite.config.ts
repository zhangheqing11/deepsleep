import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// 进化后台：独立应用，挂载在 /devconsole/。
// 开发期把 /api 转发到本地后端（VITE_DEV_PROXY_TARGET，默认 http://127.0.0.1:8000），浏览器看到的是同源请求。
// 部署方式（同源托管还是独立端口）由后端确认，见 README。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000';

  return {
    base: '/devconsole/',
    plugins: [react()],
    server: {
      port: 5174,
      strictPort: true,
      proxy: { '/api': { target: proxyTarget, changeOrigin: true } },
      // mock 模式只读引用 contracts/examples 里的正式示例 JSON。
      fs: { allow: ['.', '../contracts/examples'] },
    },
    preview: {
      port: 4174,
      strictPort: true,
      proxy: { '/api': { target: proxyTarget, changeOrigin: true } },
    },
  };
});
