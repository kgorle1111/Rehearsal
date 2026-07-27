// 10-frontend-spec.md §2.3 — typed fetch wrapper over /api/*. 11-backend-api.md §2.2 — every
// non-2xx response carries the {error:{code,message,...}} envelope; callers switch on `code`.
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    http_status: number;
    session_id?: string;
    retriable: boolean;
    detail: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  code: string;
  httpStatus: number;
  retriable: boolean;
  detail: Record<string, unknown>;

  constructor(body: ApiErrorBody['error']) {
    super(body.message);
    this.code = body.code;
    this.httpStatus = body.http_status;
    this.retriable = body.retriable;
    this.detail = body.detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...init?.headers },
  });
  if (!res.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = await res.json();
    } catch {
      /* non-JSON error body — fall through to a synthetic ApiError below */
    }
    if (body?.error) throw new ApiError(body.error);
    throw new ApiError({
      code: 'internal',
      message: `Request failed (${res.status})`,
      http_status: res.status,
      retriable: false,
      detail: {},
    });
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const http = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : '{}' }),
};
