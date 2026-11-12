const TOKEN_KEY = 'kuhhan.token';

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export type Query = Record<string, string | number | boolean | string[] | undefined | null>;

export function toQueryString(query?: Query): string {
  if (!query) return '';
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    if (Array.isArray(value)) {
      value.filter(Boolean).forEach((item) => params.append(key, item));
    } else {
      params.append(key, String(value));
    }
  });
  const text = params.toString();
  return text ? `?${text}` : '';
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`/api${path}`, { ...init, headers });
  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    if (response.status === 401) {
      const detail = (payload as { detail?: string } | null)?.detail;
      if (detail !== 'totp_required' && !path.startsWith('/auth/login')) {
        setToken(null);
        window.dispatchEvent(new CustomEvent('kuhhan:unauthorized'));
      }
    }
    const detail = (payload as { detail?: unknown } | null)?.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray((payload as { errors?: unknown })?.errors)
          ? 'Please check the submitted values'
          : `Request failed (${response.status})`;
    throw new ApiError(response.status, message, payload);
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>(`${path}${toQueryString(query)}`),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body === undefined ? undefined : JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};
