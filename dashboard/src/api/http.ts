const CSRF_COOKIE_NAME = 'stock_research_csrf';

type JsonRequestOptions = {
  credentials?: RequestCredentials;
  csrf?: boolean;
  headers?: HeadersInit;
};

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') {
    return null;
  }

  for (const part of document.cookie.split(';')) {
    const trimmed = part.trim();
    if (trimmed.startsWith(`${name}=`)) {
      return decodeURIComponent(trimmed.slice(name.length + 1));
    }
  }

  return null;
}

function getCsrfCookieName(): string {
  const override = (
    globalThis as typeof globalThis & {
      __STOCK_RESEARCH_CSRF_COOKIE_NAME__?: string;
    }
  ).__STOCK_RESEARCH_CSRF_COOKIE_NAME__;

  return override || CSRF_COOKIE_NAME;
}

function readCsrfCookie(): string | null {
  return readCookie(getCsrfCookieName());
}

function buildInit(
  method: string,
  body: unknown,
  options: JsonRequestOptions
): RequestInit | undefined {
  const init: RequestInit = {};
  const headers = new Headers(options.headers);

  if (method !== 'GET') {
    init.method = method;
  }
  if (options.credentials) {
    init.credentials = options.credentials;
  }
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
  }
  if (options.csrf) {
    const csrfToken = readCsrfCookie();
    if (csrfToken) {
      headers.set('X-CSRF-Token', csrfToken);
    }
  }
  if ([...headers.keys()].length > 0) {
    init.headers = headers;
  }

  return Object.keys(init).length > 0 ? init : undefined;
}

async function requestJson<T>(
  method: string,
  url: string,
  body: unknown,
  options: JsonRequestOptions = {}
): Promise<T> {
  const init = buildInit(method, body, options);
  const response = init === undefined ? await fetch(url) : await fetch(url, init);

  if (!response.ok) {
    throw new Error(`${method} ${url} failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function getJson<T>(url: string, options: JsonRequestOptions = {}): Promise<T> {
  return requestJson<T>('GET', url, undefined, options);
}

export function postJson<T>(url: string, body?: unknown, options: JsonRequestOptions = {}): Promise<T> {
  return requestJson<T>('POST', url, body, options);
}

export function patchJson<T>(url: string, body?: unknown, options: JsonRequestOptions = {}): Promise<T> {
  return requestJson<T>('PATCH', url, body, options);
}

export function deleteJson<T>(url: string, options: JsonRequestOptions = {}): Promise<T> {
  return requestJson<T>('DELETE', url, undefined, options);
}

export function getSessionJson<T>(url: string): Promise<T> {
  return getJson<T>(url, { credentials: 'include' });
}

export function postSessionJson<T>(
  url: string,
  body?: unknown,
  options: Omit<JsonRequestOptions, 'credentials'> = {}
): Promise<T> {
  return postJson<T>(url, body, { ...options, credentials: 'include' });
}

export function patchSessionJson<T>(
  url: string,
  body?: unknown,
  options: Omit<JsonRequestOptions, 'credentials'> = {}
): Promise<T> {
  return patchJson<T>(url, body, { ...options, credentials: 'include' });
}

export function deleteSessionJson<T>(
  url: string,
  options: Omit<JsonRequestOptions, 'credentials'> = {}
): Promise<T> {
  return deleteJson<T>(url, { ...options, credentials: 'include' });
}
