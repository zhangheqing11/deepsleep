import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';
import './shell.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// 离线缓存只在生产构建里启用：开发时不缓存，避免看到旧代码。
// 浏览器只在 https 或 localhost 下允许注册；手机通过局域网 http 访问时会跳过，不影响使用。
if (import.meta.env.PROD && 'serviceWorker' in navigator && window.isSecureContext) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => {
      /* 注册失败只影响离线使用 */
    });
  });
}
