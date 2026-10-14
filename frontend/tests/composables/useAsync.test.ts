import { describe, expect, it } from "vitest";
import { useAsync } from "@/composables/useAsync";

describe("useAsync", () => {
  it("成功返回结果并复位 busy", async () => {
    const { busy, error, run } = useAsync();
    const p = run(async () => 42);
    expect(busy.value).toBe(true);
    await expect(p).resolves.toBe(42);
    expect(busy.value).toBe(false);
    expect(error.value).toBe("");
  });

  it("失败写入 error 返回 undefined，下次运行清空 error", async () => {
    const { error, run } = useAsync();
    await expect(run(async () => { throw new Error("boom"); })).resolves.toBeUndefined();
    expect(error.value).toBe("boom");
    await run(async () => 1);
    expect(error.value).toBe("");
  });
});
