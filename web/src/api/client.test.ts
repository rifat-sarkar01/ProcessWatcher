import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createApiClient,
  errorCodeForStatus,
  readStoredAccessCode,
  SESSION_STORAGE_KEY,
  storeAccessCode,
} from "./client";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

function rawResponse(status: number): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      throw new SyntaxError("not json");
    },
  } as unknown as Response;
}

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => Array.from(map.keys())[index] ?? null,
    removeItem: (key: string) => {
      map.delete(key);
    },
    setItem: (key: string, value: string) => {
      map.set(key, value);
    },
  } as Storage;
}

async function expectApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error("expected the promise to reject with ApiError");
}

describe("createApiClient", () => {
  it("returns parsed JSON on success", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { status: "ok" }));
    const client = createApiClient({ fetchImpl });

    await expect(client.get("/runs")).resolves.toEqual({ status: "ok" });
  });

  it("joins the configured base URL and path", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, {}));
    const client = createApiClient({ baseUrl: "https://api.example/", fetchImpl });

    await client.get("/runs/run_1");

    expect(fetchImpl).toHaveBeenCalledWith(
      "https://api.example/runs/run_1",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("sends the access code when one is configured", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, {}));
    const client = createApiClient({ accessCode: "s3cret", fetchImpl });

    await client.get("/runs");

    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("X-Access-Code")).toBe("s3cret");
  });

  it("omits the access code header when none is configured", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, {}));
    const client = createApiClient({ fetchImpl });

    await client.get("/runs");

    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("X-Access-Code")).toBeNull();
  });

  it("allows the access code to be replaced at runtime", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, {}));
    const client = createApiClient({ accessCode: "old", fetchImpl });

    client.setAccessCode("new");
    await client.get("/runs");

    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("X-Access-Code")).toBe("new");
  });

  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not_found"],
    [409, "conflict"],
    [413, "too_large"],
    [422, "unprocessable"],
    [429, "rate_limited"],
    [500, "server"],
    [503, "server"],
    [418, "unknown"],
  ] as const)("maps HTTP %i to the %s error code", async (status, code) => {
    const fetchImpl = vi.fn(async () => jsonResponse(status, {}));
    const client = createApiClient({ fetchImpl });

    const error = await expectApiError(client.get("/runs"));

    expect(error.code).toBe(code);
    expect(error.status).toBe(status);
  });

  it("prefers the server-provided error message", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(413, { error: { code: "too_large", message: "Video is 612 MB." } }),
    );
    const client = createApiClient({ fetchImpl });

    const error = await expectApiError(client.get("/runs"));

    expect(error.code).toBe("too_large");
    expect(error.message).toBe("Video is 612 MB.");
  });

  it("maps a transport failure to a network error", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const client = createApiClient({ fetchImpl });

    const error = await expectApiError(client.get("/runs"));

    expect(error.code).toBe("network");
    expect(error.status).toBe(0);
  });

  it("maps a non-JSON success body to invalid_response", async () => {
    const fetchImpl = vi.fn(async () => rawResponse(200));
    const client = createApiClient({ fetchImpl });

    const error = await expectApiError(client.get("/runs"));

    expect(error.code).toBe("invalid_response");
  });

  it("survives a non-JSON error body", async () => {
    const fetchImpl = vi.fn(async () => rawResponse(502));
    const client = createApiClient({ fetchImpl });

    const error = await expectApiError(client.get("/runs"));

    expect(error.code).toBe("server");
    expect(error.message.length).toBeGreaterThan(0);
  });
});

describe("errorCodeForStatus", () => {
  it("falls back to unknown for an unmapped 4xx", () => {
    expect(errorCodeForStatus(418)).toBe("unknown");
  });

  it("maps any 5xx to server", () => {
    expect(errorCodeForStatus(599)).toBe("server");
  });
});

describe("access-code storage", () => {
  it("stores and reads the code", () => {
    const storage = memoryStorage();

    storeAccessCode("s3cret", storage);

    expect(storage.getItem(SESSION_STORAGE_KEY)).toBe("s3cret");
    expect(readStoredAccessCode(storage)).toBe("s3cret");
  });

  it("clears the code when given null", () => {
    const storage = memoryStorage();
    storeAccessCode("s3cret", storage);

    storeAccessCode(null, storage);

    expect(readStoredAccessCode(storage)).toBeNull();
  });

  it("returns null when storage throws", () => {
    const storage = {
      getItem: () => {
        throw new Error("blocked");
      },
    } as unknown as Storage;

    expect(readStoredAccessCode(storage)).toBeNull();
  });
});
