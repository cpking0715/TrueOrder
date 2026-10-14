/** 极简 fetch 封装：所有后端调用都走这里，组件不直接 fetch。 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const TOKEN_STORAGE_KEY = "trueorder_api_token";

/**
 * API 令牌（后端设置了 TRUEORDER_API_TOKEN 时必需）：
 * 优先取 localStorage（构建产物里在浏览器控制台设置一次），其次取构建期 VITE_API_TOKEN。
 */
export function getApiToken(): string {
  try {
    const stored = globalThis.localStorage?.getItem(TOKEN_STORAGE_KEY);
    if (stored) return stored;
  } catch {
    /* 隐私模式等禁用 localStorage：退回构建期变量 */
  }
  return (import.meta.env.VITE_API_TOKEN as string | undefined) ?? "";
}

export function setApiToken(token: string): void {
  globalThis.localStorage?.setItem(TOKEN_STORAGE_KEY, token);
}

function withAuth(init?: RequestInit): RequestInit | undefined {
  const token = getApiToken();
  if (!token) return init;
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers };
}

/** 浏览器直接下载（<a href>）带不了请求头：令牌放查询参数。 */
export function withApiToken(url: string): string {
  const token = getApiToken();
  if (!token) return url;
  return `${url}${url.includes("?") ? "&" : "?"}api_token=${encodeURIComponent(token)}`;
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, withAuth(init));
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText ?? ""}`.trim();
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* 非 JSON 错误体，保留状态码信息 */
    }
    if (response.status === 401) detail = `${detail}（请设置 API 令牌）`;
    throw new ApiError(response.status, detail);
  }
  // 204 / 空响应体：没有 JSON 可解析
  if (response.status === 204 || response.headers?.get("content-length") === "0") {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function uploadJson<T>(url: string, file: File, fields?: Record<string, string>): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  for (const [key, value] of Object.entries(fields ?? {})) {
    form.append(key, value);
  }
  return requestJson<T>(url, { method: "POST", body: form });
}
