import { signOut, useAuth } from '../api/auth';

/**
 * 顶栏里的“退出登录”：只在已登录时出现（后端没开登录时什么都不渲染）。
 * 样式由所在的界面给，className 传那套界面的链接样式。
 */
export function SignOutButton({ className }: { className: string }) {
  const auth = useAuth();
  if (auth.state !== 'signed-in') return null;
  return (
    <button type="button" className={className} onClick={() => void signOut()}>
      退出登录<span className="so-who">（{auth.user.display_name}）</span>
    </button>
  );
}
