import { API_ADAPTER } from '../config';
import type { ApiClient } from './client';
import { httpClient } from './httpClient';
import { mockClient } from './mockClient';
import { withRequestLog } from './requestLog';

// 由配置决定数据来源，运行期不切换：真实请求失败时绝不回退到模拟数据。
export const api: ApiClient = withRequestLog(API_ADAPTER === 'http' ? httpClient : mockClient);
