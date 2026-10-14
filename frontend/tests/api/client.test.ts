/** api/client：令牌注入、204 空响应、错误详情、下载链接带令牌。 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, requestJson, setApiToken, withApiToken } from "@/api/client";

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

function stubFetch(res: Partial<Response> & { json?: () => Promise<unknown> }) {
  const fn = vi.fn().mockResolvedValue({ ok: true, status: 200, ...res });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("requestJson", () => {
  it("204 返回 undefined 不解析 JSON", async () => {
    const json = vi.fn();
    stubFetch({ status: 204, json });
    await expect(requestJson("/api/x", { method: "DELETE" })).resolves.toBeUndefined();
    expect(json).not.toHaveBeenCalled();
  });

  it("有令牌时带 Authorization 头，并保留原有头", async () => {
    setApiToken("tok");
    const fn = stubFetch({ json: async () => ({ a: 1 }) });
    await requestJson("/api/x", { headers: { "Content-Type": "application/json" } });
    const headers = new Headers(fn.mock.calls[0][1].headers);
    expect(headers.get("Authorization")).toBe("Bearer tok");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("无令牌时不改请求", async () => {
    const fn = stubFetch({ json: async () => ({}) });
    await requestJson("/api/x");
    expect(fn.mock.calls[0][1]).toBeUndefined();
  });

  it("错误抛 ApiError 带后端 detail；401 提示设置令牌", async () => {
    stubFetch({ ok: false, status: 401, json: async () => ({ detail: "缺少令牌" }) });
    const err = (await requestJson("/api/x").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(err.message).toContain("缺少令牌");
    expect(err.message).toContain("API 令牌");
  });
});

describe("withApiToken", () => {
  it("无令牌原样返回", () => {
    expect(withApiToken("/api/a.csv?x=1")).toBe("/api/a.csv?x=1");
  });

  it("有令牌追加查询参数", () => {
    setApiToken("a b");
    expect(withApiToken("/api/a.csv?x=1")).toBe("/api/a.csv?x=1&api_token=a%20b");
    expect(withApiToken("/api/a.csv")).toBe("/api/a.csv?api_token=a%20b");
  });
});
