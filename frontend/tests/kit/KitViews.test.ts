/** 组件：任务台跳转链接、开发信只生成不发送、询盘状态流与 PI 链接、买家导入摘要。 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import * as api from "@/api/kit";
import KitBuyersView from "@/features/kit/views/KitBuyersView.vue";
import KitDraftsView from "@/features/kit/views/KitDraftsView.vue";
import KitInquiriesView from "@/features/kit/views/KitInquiriesView.vue";
import KitTodayView from "@/features/kit/views/KitTodayView.vue";
import { buyer, draft, inquiry, profile, tasks } from "./fixtures";

vi.mock("@/api/kit", async (orig) => {
  const actual = await orig<typeof import("@/api/kit")>();
  return {
    ...actual,
    fetchKitTasks: vi.fn(), setKitTaskDone: vi.fn(), fetchKitProfiles: vi.fn(),
    fetchKitBuyers: vi.fn(), importKitBuyers: vi.fn(), patchKitBuyer: vi.fn(),
    createKitDraft: vi.fn(), fetchKitDrafts: vi.fn(), fetchKitInquiries: vi.fn(),
    createKitInquiry: vi.fn(), setInquiryStatus: vi.fn(),
  };
});

function mount(component: object) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:p(.*)*", component: { template: "<div />" } }] });
  return render(component, { global: { plugins: [router] } });
}

beforeEach(() => {
  vi.mocked(api.fetchKitTasks).mockResolvedValue(structuredClone(tasks));
  vi.mocked(api.fetchKitProfiles).mockResolvedValue([profile]);
  vi.mocked(api.fetchKitBuyers).mockResolvedValue([buyer]);
  vi.mocked(api.fetchKitDrafts).mockResolvedValue([]);
  vi.mocked(api.fetchKitInquiries).mockResolvedValue([inquiry]);
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("出海包页面", () => {
  it("任务台：显示今天与进度，站内任务带跳转、站外任务不带", async () => {
    mount(KitTodayView);
    expect((await screen.findByTestId("kit-progress")).textContent).toContain("今天是第 2 天 · 已完成 1/3");
    const links = screen.getAllByRole("link", { name: "去处理 →" });
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("/kit/products");
    expect(screen.getByText("站外操作")).toBeTruthy();
  });

  it("开发信：带上买家首个联系人生成，页面没有发送按钮", async () => {
    vi.mocked(api.createKitDraft).mockResolvedValue(draft);
    mount(KitDraftsView);
    await screen.findByRole("option", { name: profile.name });
    await fireEvent.update(screen.getByLabelText("产品"), "1");
    await fireEvent.update(screen.getByLabelText("买家"), "9");
    await fireEvent.click(screen.getByRole("button", { name: "生成草稿" }));
    await waitFor(() => expect(api.createKitDraft).toHaveBeenCalledWith({
      product_id: 1, company_id: 9, channel: "email", contact_id: 77,
    }));
    expect((await screen.findByTestId("kit-draft-5")).textContent).toContain("下次 2026-10-19");
    expect(screen.queryByRole("button", { name: /发送/ })).toBeNull();
  });

  it("询盘：只给合法下一步，PI 链接指向 pdf", async () => {
    vi.mocked(api.setInquiryStatus).mockResolvedValue({ ...inquiry, status: "quoted", status_label: "已报价" });
    mount(KitInquiriesView);
    const row = await screen.findByTestId("kit-inquiry-3");
    expect((row).textContent).toContain("USD 1950.00");
    expect(screen.queryByRole("button", { name: "→ 赢单" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "→ 已报价" }));
    await waitFor(() => expect(api.setInquiryStatus).toHaveBeenCalledWith(3, "quoted"));
    expect(await screen.findByText("已报价", { selector: ".badge" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "导出 PI" }).getAttribute("href")).toBe("/api/kit/inquiries/3/pi.pdf");
  });

  it("买家：导入后显示摘要与错误行", async () => {
    vi.mocked(api.importKitBuyers).mockResolvedValue({
      rows_valid: 50, companies_created: 50, buyers_tagged: 50, already_in_library: 0,
      contacts_added: 50, duplicates_in_file: 2, errors: ["第 54 行：邮箱格式非法 'broken@'"],
    });
    mount(KitBuyersView);
    const input = await screen.findByTestId("kit-buyer-file");
    const file = new File(["company_name,country\n"], "b.csv", { type: "text/csv" });
    await fireEvent.update(input, "");
    Object.defineProperty(input, "files", { value: [file] });
    await fireEvent.change(input);
    expect((await screen.findByTestId("kit-import-summary")).textContent).toContain("新增 50 家");
    expect(screen.getByText(/邮箱格式非法/)).toBeTruthy();
  });
});
