/** 开发信发送区冒烟：空态 / 有联系人时露出预览控件。 */

import { cleanup, render, screen, waitFor } from "@testing-library/vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import SendEmailSection from "@/features/outreach/components/SendEmailSection.vue";
import { fetchTemplates } from "@/api/outreach";
import type { Opportunity } from "@/api/opportunities";
import type { Contact } from "@/api/contacts";

vi.mock("@/api/outreach", () => ({
  fetchTemplates: vi.fn(),
  previewEmail: vi.fn(),
  queueSend: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const opportunity = {
  opportunity_id: 1,
  product_id: 10,
  company_id: 100,
  company_name: "ACME",
  stage: "lead",
  intent: "cold",
  next_follow_up_on: null,
  owner_note: "",
  closed_reason: null,
} as Opportunity;

describe("SendEmailSection", () => {
  it("无邮箱联系人时提示补全", async () => {
    vi.mocked(fetchTemplates).mockResolvedValue([]);
    render(SendEmailSection, { props: { opportunity, contacts: [] } });
    await waitFor(() => expect(fetchTemplates).toHaveBeenCalled());
    expect(screen.getByText(/暂无带邮箱的联系人/)).toBeTruthy();
  });

  it("有邮箱与模板时显示预览按钮", async () => {
    vi.mocked(fetchTemplates).mockResolvedValue([
      { id: 3, name: "Intro", subject: "Hi", body: "Hello", language: "en" },
    ]);
    const contacts = [
      {
        contact_id: 9,
        company_id: 100,
        name: "Ada",
        title: "Buyer",
        email: "ada@acme.com",
        phone: null,
        is_generic: false,
        source: "finder",
        source_ref: "hunter",
        acquired_at: "2026-01-01T00:00:00Z",
        verify_status: "unknown",
        do_not_contact: false,
      },
    ] as Contact[];
    render(SendEmailSection, { props: { opportunity, contacts } });
    await waitFor(() => expect(screen.getByTestId("preview-email")).toBeTruthy());
    expect(screen.getByText(/Ada/)).toBeTruthy();
    expect(screen.getByText(/Intro/)).toBeTruthy();
  });
});
