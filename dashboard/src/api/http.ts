const DEFAULT_CSRF_COOKIE_NAME =
  import.meta.env.VITE_STOCK_RESEARCH_CSRF_COOKIE_NAME?.trim() || 'stock_research_csrf';
let csrfCookieName = DEFAULT_CSRF_COOKIE_NAME;

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

export function setCsrfCookieName(name: string): void {
  csrfCookieName = name.trim() || DEFAULT_CSRF_COOKIE_NAME;
}

function readCsrfCookie(): string | null {
  return readCookie(csrfCookieName);
}

async function readResponseText(response: Response): Promise<string> {
  if (typeof response.text !== 'function') {
    return '';
  }

  return await response.text();
}

function readErrorDetailFromJson(text: string): string {
  try {
    const payload = JSON.parse(text) as {
      detail?: unknown;
      message?: unknown;
    };

    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail.trim();
    }
    if (typeof payload.message === 'string' && payload.message.trim()) {
      return payload.message.trim();
    }
  } catch {
    return '';
  }

  return '';
}

async function buildErrorMessage(method: string, url: string, response: Response): Promise<string> {
  const prefix = `${method} ${url} failed with ${response.status}`;
  const contentType = response.headers?.get?.('content-type') ?? '';
  const responseText = (await readResponseText(response)).trim();
  const detail = contentType.includes('application/json')
    ? readErrorDetailFromJson(responseText) || responseText
    : responseText;

  return detail ? `${prefix}: ${detail}` : prefix;
}

async function readSuccessPayload<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }

  const responseText = await readResponseText(response);
  if (responseText) {
    return JSON.parse(responseText) as T;
  }

  if (typeof response.json === 'function') {
    return response.json() as Promise<T>;
  }

  return undefined as T;
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
    throw new Error(await buildErrorMessage(method, url, response));
  }

  return readSuccessPayload<T>(response);
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
