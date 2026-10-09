/** 极简 fetch 封装：所有后端调用都走这里，组件不直接 fetch。 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* 非 JSON 错误体，保留状态码信息 */
    }
    throw new ApiError(response.status, detail);
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
