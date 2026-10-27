/**
 * Typed API client for the Process Watcher API (05_Schema §13, 04_TRD §8).
 *
 * Until `openapi.json` lands (T-5.2) the routes are thin and generic; what matters
 * here is the error contract: every HTTP failure becomes a typed `ApiError` with a
 * stable code, so UI states (unauthorized / not found / too large / conflict / …)
 * are decided by code, never by matching message text.
 */

export type ApiErrorCode =
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "too_large"
  | "conflict"
  | "unprocessable"
  | "rate_limited"
  | "server"
  | "unknown"
  | "network"
  | "invalid_response";

const STATUS_TO_CODE: Record<number, ApiErrorCode> = {
  401: "unauthorized",
  403: "forbidden",
  404: "not_found",
  409: "conflict",
  413: "too_large",
  422: "unprocessable",
  429: "rate_limited",
};

const DEFAULT_MESSAGE: Record<ApiErrorCode, string> = {
  unauthorized: "That access code was not accepted.",
  forbidden: "You are not allowed to access this run.",
  not_found: "That run or artifact does not exist.",
  too_large: "That upload is larger than the 500 MB limit.",
  conflict: "The run is not ready yet.",
  unprocessable: "The request could not be validated.",
  rate_limited: "Too many requests. Wait a moment and try again.",
  server: "The Process Watcher API failed. Try again.",
  unknown: "The API returned an unexpected response.",
  network: "Could not reach the Process Watcher API.",
  invalid_response: "The API returned a response that is not valid JSON.",
};

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;

  constructor(code: ApiErrorCode, status: number, message?: string) {
    super(message ?? DEFAULT_MESSAGE[code]);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export function errorCodeForStatus(status: number): ApiErrorCode {
  const known = STATUS_TO_CODE[status];
  if (known) return known;
  if (status >= 500) return "server";
  return "unknown";
}

export interface ApiClientOptions {
  /** Same-origin by default; set VITE_API_BASE for a separate API host. */
  baseUrl?: string;
  accessCode?: string | null;
  fetchImpl?: typeof fetch;
}

export interface ApiClient {
  setAccessCode(code: string | null): void;
  get<R = unknown>(path: string, init?: RequestInit): Promise<R>;
}

export const SESSION_STORAGE_KEY = "pw.access-code";

function joinUrl(baseUrl: string, path: string): string {
  const base = baseUrl.replace(/\/+$/, "");
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${base}${suffix}`;
}

async function readErrorMessage(response: Response): Promise<string | null> {
  try {
    const payload: unknown = await response.json();
    if (payload && typeof payload === "object" && "error" in payload) {
      const error = (payload as { error?: unknown }).error;
      if (error && typeof error === "object" && "message" in error) {
        const message = (error as { message?: unknown }).message;
        if (typeof message === "string" && message.length > 0) return message;
      }
    }
  } catch {
    // Body was not JSON: fall back to the default message for the status.
  }
  return null;
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = options.baseUrl ?? "";
  const fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  let accessCode = options.accessCode ?? null;

  return {
    setAccessCode(code: string | null): void {
      accessCode = code;
    },

    async get<R = unknown>(path: string, init?: RequestInit): Promise<R> {
      const headers = new Headers(init?.headers);
      headers.set("Accept", "application/json");
      if (accessCode) headers.set("X-Access-Code", accessCode);

      let response: Response;
      try {
        response = await fetchImpl(joinUrl(baseUrl, path), { ...init, headers });
      } catch {
        throw new ApiError("network", 0);
      }

      if (!response.ok) {
        const detail = await readErrorMessage(response);
        throw new ApiError(errorCodeForStatus(response.status), response.status, detail ?? undefined);
      }

      try {
        return (await response.json()) as R;
      } catch {
        throw new ApiError("invalid_response", response.status);
      }
    },
  };
}

/** Read the access code remembered for this browser session (if any). */
export function readStoredAccessCode(storage: Storage = sessionStorage): string | null {
  try {
    return storage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Remember the access code for this browser session. */
export function storeAccessCode(code: string | null, storage: Storage = sessionStorage): void {
  try {
    if (code) storage.setItem(SESSION_STORAGE_KEY, code);
    else storage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Storage can be unavailable (private mode); the gate still works per request.
  }
}
