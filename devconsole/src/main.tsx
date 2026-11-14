import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles.css';

// 进化后台不注册 Service Worker：它只读实时数据，离线时应当明确断连，而不是显示缓存页面。
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
