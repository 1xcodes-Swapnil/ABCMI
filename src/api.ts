// One authenticated transport for every production screen. Tokens stay in memory.
let bearer = '';
let tenant = '';
export function credentials(token: string, tenantId: string) { bearer = token; tenant = tenantId; }
export async function response(path: string, init: RequestInit = {}) {
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('://')) throw new Error('Only this application API is allowed');
  const headers = new Headers(init.headers);
  if (bearer) headers.set('Authorization', `Bearer ${bearer}`);
  if (tenant) headers.set('X-Tenant-ID', tenant);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const res = await fetch(`/api/v1${path}`, {...init, headers});
  if (!res.ok) {
    const body = await res.text();
    let message = body;
    try { const data = JSON.parse(body); message = data.error?.message || data.detail || data.message || body; } catch { /* Non-JSON error */ }
    throw new Error(`HTTP ${res.status}: ${typeof message === 'string' ? message : JSON.stringify(message)}`);
  }
  return res;
}
export async function api<T = any>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await response(path, init);
  if (res.status === 204) return null as T;
  return res.json();
}
export const write = (path: string, body?: unknown, method = 'POST') => api(path, {method, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
export function download(data: Blob, name: string) {
  const url = URL.createObjectURL(data), a = document.createElement('a'); a.href = url; a.download = name;
  a.style.display = 'none'; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
export const rows = (data: any): any[] => Array.isArray(data) ? data : data?.items || data?.results || data?.queries || data?.notifications || [];
