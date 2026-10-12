/** WP2 组件测试：看板渲染/换阶段/流失原因与抽屉跟进区（不打真实后端）。 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PipelineView from "@/features/pipeline/views/PipelineView.vue";
import FollowUpSection from "@/features/pipeline/components/FollowUpSection.vue";
import {
  addActivity,
  fetchOpportunities,
  fetchTimeline,
  patchOpportunity,
  type Opportunity,
} from "@/api/opportunities";
import { fetchProducts } from "@/api/products";

vi.mock("@/api/opportunities", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/opportunities")>();
  return {
    ...actual,
    fetchOpportunities: vi.fn(),
    patchOpportunity: vi.fn(),
    addActivity: vi.fn(),
    fetchTimeline: vi.fn(),
  };
});
vi.mock("@/api/products", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/products")>();
  return { ...actual, fetchProducts: vi.fn() };
});

const opp = (over: Partial<Opportunity> = {}): Opportunity => ({
  opportunity_id: 1,
  product_id: 10,
  company_id: 100,
  company_name: "BROOKLYN APPAREL LLC",
  stage: "lead",
  intent: "cold",
  next_follow_up_on: null,
  owner_note: "",
  closed_reason: null,
  ...over,
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("PipelineView 看板", () => {
  beforeEach(() => {
    vi.mocked(fetchProducts).mockResolvedValue([]);
  });

  it("按阶段分列渲染卡片与数量", async () => {
    vi.mocked(fetchOpportunities).mockResolvedValue([
      opp({ opportunity_id: 1, stage: "lead" }),
      opp({ opportunity_id: 2, company_name: "PACIFIC FASHION", stage: "replied" }),
    ]);
    render(PipelineView);
    expect(await screen.findByTestId("card-1")).toBeTruthy();
    expect(screen.getByTestId("col-lead").textContent).toContain("BROOKLYN APPAREL");
    expect(screen.getByTestId("col-replied").textContent).toContain("PACIFIC FASHION");
    expect(screen.getByTestId("col-lead").textContent).toContain("1");  // 列计数
  });

  it("今日待跟进横幅只含到期商机", async () => {
    const today = new Date().toISOString().slice(0, 10);
    vi.mocked(fetchOpportunities).mockResolvedValue([
      opp({ opportunity_id: 1, stage: "contacted", next_follow_up_on: today }),
      opp({ opportunity_id: 2, company_name: "FUTURE CO", next_follow_up_on: "2099-01-01" }),
    ]);
    render(PipelineView);
    await screen.findByText("FUTURE CO");
    const banner = screen.getByTestId("due-today");
    expect(banner.textContent).toContain("BROOKLYN APPAREL");
    expect(banner.textContent).not.toContain("FUTURE CO");
  });

  it("推进按钮调 PATCH 下一阶段；流失按钮展开原因表单", async () => {
    vi.mocked(fetchOpportunities)
      .mockResolvedValueOnce([opp()])
      .mockResolvedValue([opp({ stage: "contacted" })]);
    vi.mocked(patchOpportunity).mockResolvedValue(opp({ stage: "contacted" }));
    render(PipelineView);
    await screen.findByTestId("card-1");

    // 点推进 → PATCH contacted（lead 的下一阶段）
    const advanceBtn = screen.getByTestId("card-1").querySelector("button[title*='推进']");
    expect(advanceBtn).toBeTruthy();
    await fireEvent.click(advanceBtn!);
    await waitFor(() => {
      expect(patchOpportunity).toHaveBeenCalledWith(1, { stage: "contacted" });
    });

    // 点流失 → 展开原因表单，空原因确认按钮禁用
    const lostBtn = screen.getByTestId("card-1").querySelector("button[title*='流失']");
    expect(lostBtn).toBeTruthy();
    await fireEvent.click(lostBtn!);
    expect(await screen.findByTestId("lost-form")).toBeTruthy();
    const confirmBtn = screen.getByText("确认流失");
    expect((confirmBtn as HTMLButtonElement).disabled).toBe(true);
    await fireEvent.update(screen.getByTestId("lost-reason"), "无回复");
    expect((screen.getByText("确认流失") as HTMLButtonElement).disabled).toBe(false);
    vi.mocked(patchOpportunity).mockClear();
    await fireEvent.click(screen.getByText("确认流失"));
    await waitFor(() => {
      expect(patchOpportunity).toHaveBeenCalledWith(1, {
        stage: "lost",
        closed_reason: "无回复",
      });
    });
  });
});

describe("FollowUpSection 抽屉跟进区", () => {
  it("时间线渲染与记录活动", async () => {
    vi.mocked(fetchTimeline).mockResolvedValue([
      {
        activity_id: 5, opportunity_id: 1, contact_id: null, kind: "call",
        summary: "通了电话", body: "", intent_after: "warm", occurred_at: "2026-10-12T10:00:00",
      },
    ]);
    vi.mocked(addActivity).mockResolvedValue({
      activity_id: 6, opportunity_id: 1, contact_id: null, kind: "note",
      summary: "新备注", body: "", intent_after: null, occurred_at: "2026-10-12T11:00:00",
    });
    render(FollowUpSection, { props: { opportunity: opp() } });
    expect(await screen.findByText("通了电话")).toBeTruthy();
    expect(screen.getByText("→ warm")).toBeTruthy();

    await fireEvent.update(screen.getByTestId("activity-summary"), "新备注");
    await fireEvent.click(screen.getByTestId("activity-submit"));
    await waitFor(() => expect(addActivity).toHaveBeenCalledWith(1, {
      kind: "note", summary: "新备注", intent_after: undefined,
    }));
  });
});
