/** api/jobs：导入任务轮询（完成返回 result、失败抛错、超时引导去任务页）。 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { JobStillRunningError, waitForJob } from "@/api/jobs";
import { uploadBillsCsv } from "@/api/products";

afterEach(() => vi.unstubAllGlobals());

function stubJobs(...bodies: unknown[]) {
  const fn = vi.fn();
  for (const body of bodies) fn.mockResolvedValueOnce({ ok: true, status: 200, json: async () => body });
  vi.stubGlobal("fetch", fn);
  return fn;
}

const noSleep = { sleep: async () => undefined, intervalMs: 1, timeoutMs: 3 };

describe("waitForJob", () => {
  it("pending → done 返回 result", async () => {
    const fn = stubJobs({ status: "pending" }, { status: "running" }, { status: "done", result: { added: 2 } });
    await expect(waitForJob(7, noSleep)).resolves.toEqual({ added: 2 });
    expect(fn).toHaveBeenCalledTimes(3);
    expect(fn.mock.calls[0][0]).toBe("/api/jobs/7");
  });

  it("failed 抛 last_error", async () => {
    stubJobs({ status: "failed", last_error: "上传暂存已不存在" });
    await expect(waitForJob(7, noSleep)).rejects.toThrow("上传暂存已不存在");
  });

  it("超时抛 JobStillRunningError", async () => {
    stubJobs({ status: "pending" }, { status: "pending" }, { status: "pending" });
    await expect(waitForJob(7, noSleep)).rejects.toBeInstanceOf(JobStillRunningError);
  });
});

describe("uploadBillsCsv", () => {
  it("上传拿 job_id 后轮询结果", async () => {
    const fn = stubJobs({ job_id: 9, status: "queued" }, { status: "done", result: { inserted_bills: 3 } });
    const file = new File(["a,b\n"], "b.csv", { type: "text/csv" });
    await expect(uploadBillsCsv(file, "2026-10-09", noSleep)).resolves.toEqual({ inserted_bills: 3 });
    expect(fn.mock.calls[0][0]).toBe("/api/bills/import");
    expect(fn.mock.calls[1][0]).toBe("/api/jobs/9");
  });
});
