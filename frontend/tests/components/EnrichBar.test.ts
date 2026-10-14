/** WP4 组件测试：批量补全两段式（估计→确认）与抽屉查找按钮（不打真实后端）。 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import EnrichBar from "@/features/products/components/EnrichBar.vue";
import ContactsPanel from "@/features/products/components/ContactsPanel.vue";
import {
  enrichBuyers,
  fetchContacts,
  requestFindContacts,
  fetchEnrichUsage,
} from "@/api/contacts";

vi.mock("@/api/contacts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contacts")>();
  return {
    ...actual,
    enrichBuyers: vi.fn(),
    requestFindContacts: vi.fn(),
    fetchEnrichUsage: vi.fn(),
    fetchContacts: vi.fn(),
    createContact: vi.fn(),
    updateContact: vi.fn(),
    deleteContact: vi.fn(),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("EnrichBar 批量补全", () => {
  it("先估计后确认，confirm 请求带 confirm=true", async () => {
    vi.mocked(fetchEnrichUsage).mockResolvedValue({
      provider: "fake", configured: false, daily_cap: 20, used_today: 0, remaining: 20,
    });
    vi.mocked(enrichBuyers)
      .mockResolvedValueOnce({
        candidates: 3, skipped_has_contacts: 1, skipped_queried_recently: 1,
        capped_by_quota: 0, credits_needed: 3, daily_cap: 20, used_today: 0,
        enqueued: 0, job_ids: [],
      })
      .mockResolvedValueOnce({
        candidates: 3, skipped_has_contacts: 1, skipped_queried_recently: 1,
        capped_by_quota: 0, credits_needed: 3, daily_cap: 20, used_today: 0,
        enqueued: 3, job_ids: [1, 2, 3],
      });

    render(EnrichBar, { props: { productId: 1, query: { tier: "precise" } } });
    await fireEvent.click(screen.getByTestId("enrich-estimate"));

    const text = await screen.findByTestId("enrich-estimate-text");
    expect(text.textContent).toContain("可补全 3 家");
    expect(text.textContent).toContain("已有联系人跳过 1");
    // 估计请求不带 confirm
    expect(enrichBuyers).toHaveBeenCalledWith(1, expect.objectContaining({ confirm: false }));

    await fireEvent.click(screen.getByTestId("enrich-confirm"));
    expect(await screen.findByTestId("enrich-executed")).toBeTruthy();
    expect(enrichBuyers).toHaveBeenLastCalledWith(1, expect.objectContaining({ confirm: true }));
  });

  it("额度耗尽仍可确认入队，文案讲延期而非截断", async () => {
    vi.mocked(fetchEnrichUsage).mockResolvedValue({
      provider: "fake", configured: false, daily_cap: 20, used_today: 20, remaining: 0,
    });
    vi.mocked(enrichBuyers).mockResolvedValueOnce({
      candidates: 5, skipped_has_contacts: 0, skipped_queried_recently: 0,
      capped_by_quota: 5, credits_needed: 5, daily_cap: 20, used_today: 20,
      enqueued: 0, job_ids: [],
    });
    render(EnrichBar, { props: { productId: 1, query: {} } });
    await fireEvent.click(screen.getByTestId("enrich-estimate"));
    const text = await screen.findByTestId("enrich-estimate-text");
    expect(text.textContent).toContain("延期到明日");
    expect(text.textContent).toContain("免费源命中则不消耗");
    expect((screen.getByTestId("enrich-confirm") as HTMLButtonElement).disabled).toBe(false);
  });

  it("估计为 0 时确认按钮禁用", async () => {
    vi.mocked(fetchEnrichUsage).mockResolvedValue({
      provider: "fake", configured: false, daily_cap: 20, used_today: 20, remaining: 0,
    });
    vi.mocked(enrichBuyers).mockResolvedValueOnce({
      candidates: 0, skipped_has_contacts: 5, skipped_queried_recently: 0,
      capped_by_quota: 0, credits_needed: 0, daily_cap: 20, used_today: 20,
      enqueued: 0, job_ids: [],
    });
    render(EnrichBar, { props: { productId: 1, query: {} } });
    await fireEvent.click(screen.getByTestId("enrich-estimate"));
    await screen.findByTestId("enrich-estimate-text");
    expect((screen.getByTestId("enrich-confirm") as HTMLButtonElement).disabled).toBe(true);
  });

  it("估计失败显示错误", async () => {
    vi.mocked(fetchEnrichUsage).mockRejectedValue(new Error("ignore"));
    vi.mocked(enrichBuyers).mockRejectedValue(new Error("后端不可用"));
    render(EnrichBar, { props: { productId: 1, query: {} } });
    await fireEvent.click(screen.getByTestId("enrich-estimate"));
    expect(await screen.findByText(/后端不可用/)).toBeTruthy();
  });
});

describe("ContactsPanel 查找按钮", () => {
  it("查找联系方式入队并显示任务提示", async () => {
    vi.mocked(fetchContacts).mockResolvedValue([]);
    vi.mocked(requestFindContacts).mockResolvedValue({ job_id: 7, kind: "find_contacts" });
    render(ContactsPanel, { props: { companyId: 9 } });
    await fireEvent.click(screen.getByTestId("find-contacts"));
    expect(requestFindContacts).toHaveBeenCalledWith(9, "finder", undefined);
    const hint = await screen.findByTestId("enqueued-hint");
    expect(hint.textContent).toContain("#7");
  });

  it("产品上下文下查找带 productId", async () => {
    vi.mocked(fetchContacts).mockResolvedValue([]);
    vi.mocked(requestFindContacts).mockResolvedValue({ job_id: 8, kind: "crawl_website" });
    render(ContactsPanel, { props: { companyId: 9, productId: 4 } });
    await fireEvent.click(screen.getByTestId("find-contacts"));
    expect(requestFindContacts).toHaveBeenCalledWith(9, "finder", 4);
  });

  it("抓取官网走 website 方法", async () => {
    vi.mocked(fetchContacts).mockResolvedValue([]);
    vi.mocked(requestFindContacts).mockResolvedValue({ job_id: 8, kind: "crawl_website" });
    render(ContactsPanel, { props: { companyId: 9 } });
    await fireEvent.click(screen.getByTestId("crawl-website"));
    await waitFor(() => {
      expect(requestFindContacts).toHaveBeenCalledWith(9, "website", undefined);
    });
  });
});
