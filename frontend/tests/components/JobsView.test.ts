/** 组件测试：任务状态页的渲染、过滤与空态（不打真实后端）。 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import JobsView from "@/features/jobs/views/JobsView.vue";
import { fetchJobs, type JobList } from "@/api/jobs";

vi.mock("@/api/jobs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/jobs")>();
  return { ...actual, fetchJobs: vi.fn() };
});

const fixture: JobList = {
  total: 2,
  items: [
    {
      id: 3,
      kind: "find_contacts",
      payload: { company_id: 9 },
      status: "done",
      attempts: 1,
      max_attempts: 3,
      run_after: "2026-10-10T12:00:00Z",
      last_error: null,
      created_at: "2026-10-10T11:59:00Z",
    },
    {
      id: 2,
      kind: "crawl_website",
      payload: {},
      status: "failed",
      attempts: 3,
      max_attempts: 3,
      run_after: "2026-10-10T12:05:00Z",
      last_error: "RuntimeError: network down",
      created_at: "2026-10-10T11:58:00Z",
    },
  ],
};

beforeEach(() => {
  vi.mocked(fetchJobs).mockResolvedValue(fixture);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("JobsView", () => {
  it("渲染任务行：类型中文化、状态徽章、失败原因", async () => {
    render(JobsView);
    expect(await screen.findByTestId("jobs-table")).toBeTruthy();
    expect(screen.getByText("查找联系人")).toBeTruthy();
    expect(screen.getByText("抓取官网")).toBeTruthy();
    expect(screen.getByText("RuntimeError: network down")).toBeTruthy();
    const table = screen.getByTestId("jobs-table").textContent ?? "";
    expect(table).toContain("3/3");
  });

  it("状态过滤按钮带参数调用 API", async () => {
    render(JobsView);
    await screen.findByTestId("jobs-table");
    await fireEvent.click(screen.getByTestId("job-filter-failed"));
    await waitFor(() => {
      expect(fetchJobs).toHaveBeenCalledWith("failed");
    });
  });

  it("空结果与失败请求的可见状态", async () => {
    vi.mocked(fetchJobs).mockResolvedValue({ total: 0, items: [] });
    render(JobsView);
    expect(await screen.findByTestId("jobs-empty")).toBeTruthy();

    vi.mocked(fetchJobs).mockRejectedValue(new Error("后端不可用"));
    await fireEvent.click(screen.getByTestId("job-filter-all"));
    expect(await screen.findByText(/加载任务失败：后端不可用/)).toBeTruthy();
  });
});
