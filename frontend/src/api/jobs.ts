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
