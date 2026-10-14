/** 任务域 API：类型来自后端 OpenAPI 生成，组件不直接 fetch。 */

import { requestJson } from "./client";
import type { components } from "./schema";

export type Job = components["schemas"]["JobOut"];
export type JobList = components["schemas"]["JobsListOut"];
export type JobStatus = "pending" | "running" | "done" | "failed";

export async function fetchJobs(status?: JobStatus): Promise<JobList> {
  const search = status ? `?status=${status}` : "";
  return requestJson<JobList>(`/api/jobs${search}`);
}

export type ImportJob = components["schemas"]["ImportJobOut"];

export async function fetchJob(jobId: number): Promise<Job> {
  return requestJson<Job>(`/api/jobs/${jobId}`);
}

/** 轮询超时：任务仍在后台跑，引导用户去任务页看结果。 */
export class JobStillRunningError extends Error {
  constructor(public readonly jobId: number) {
    super(`任务 #${jobId} 仍在后台处理，可稍后到「任务」页查看结果`);
  }
}

export interface WaitOptions {
  intervalMs?: number;
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** 轮询单个任务直到完成；失败抛出 last_error，超时抛 JobStillRunningError。返回 result。 */
export async function waitForJob<T>(jobId: number, options: WaitOptions = {}): Promise<T> {
  const { intervalMs = 1000, timeoutMs = 120_000, sleep = defaultSleep } = options;
  const attempts = Math.max(1, Math.ceil(timeoutMs / intervalMs));
  for (let i = 0; i < attempts; i += 1) {
    const job = await fetchJob(jobId);
    if (job.status === "done") return (job.result ?? {}) as T;
    if (job.status === "failed") throw new Error(job.last_error || `任务 #${jobId} 失败`);
    await sleep(intervalMs);
  }
  throw new JobStillRunningError(jobId);
}
