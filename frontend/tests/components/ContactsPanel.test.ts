/** ContactsPanel 组件测试：列表渲染、新增、标记不再联系、删除、错误态。 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ContactsPanel from "@/features/products/components/ContactsPanel.vue";
import {
  createContact,
  deleteContact,
  fetchContacts,
  updateContact,
  type Contact,
} from "@/api/contacts";

vi.mock("@/api/contacts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/contacts")>();
  return {
    ...actual,
    fetchContacts: vi.fn(),
    createContact: vi.fn(),
    updateContact: vi.fn(),
    deleteContact: vi.fn(),
  };
});

function contactFixture(overrides: Partial<Contact> = {}): Contact {
  return {
    contact_id: 1,
    company_id: 10,
    name: "John Smith",
    title: "Purchasing Manager",
    email: "john@example.com",
    phone: null,
    is_generic: false,
    source: "manual",
    source_ref: "",
    acquired_at: "2026-10-10T00:00:00Z",
    verify_status: "unknown",
    do_not_contact: false,
    ...overrides,
  };
}

describe("ContactsPanel", () => {
  beforeEach(() => {
    vi.mocked(fetchContacts).mockReset();
    vi.mocked(createContact).mockReset();
    vi.mocked(updateContact).mockReset();
    vi.mocked(deleteContact).mockReset();
  });
  afterEach(cleanup);

  it("渲染联系人列表与通用邮箱标签", async () => {
    vi.mocked(fetchContacts).mockResolvedValue([
      contactFixture(),
      contactFixture({ contact_id: 2, name: null, email: "sales@example.com", is_generic: true }),
    ]);
    render(ContactsPanel, { props: { companyId: 10 } });
    await screen.findByTestId("contact-row-1");
    expect(screen.getByText("John Smith")).toBeTruthy();
    expect(screen.getByText("（通用邮箱）")).toBeTruthy();
    expect(screen.getByText("通用邮箱")).toBeTruthy();
    expect(screen.getByText("联系人（2）")).toBeTruthy();
  });

  it("新增联系人提交后刷新列表", async () => {
    vi.mocked(fetchContacts)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([contactFixture()]);
    vi.mocked(createContact).mockResolvedValue(contactFixture());
    render(ContactsPanel, { props: { companyId: 10 } });
    await screen.findByText(/暂无联系人/);
    await fireEvent.click(screen.getByTestId("add-contact"));
    await fireEvent.update(screen.getByTestId("contact-name"), "John Smith");
    await fireEvent.update(screen.getByTestId("contact-email"), "john@example.com");
    await fireEvent.submit(screen.getByTestId("contact-form"));
    await waitFor(() => expect(createContact).toHaveBeenCalledWith(10, {
      name: "John Smith", title: "", email: "john@example.com", phone: null,
    }));
    await screen.findByTestId("contact-row-1");
  });

  it("标记不再联系调用更新并刷新", async () => {
    vi.mocked(fetchContacts).mockResolvedValue([contactFixture()]);
    vi.mocked(updateContact).mockResolvedValue(contactFixture({ do_not_contact: true }));
    render(ContactsPanel, { props: { companyId: 10 } });
    await screen.findByTestId("contact-row-1");
    expect(screen.queryByTestId("dnc-badge")).toBeNull();
    await fireEvent.click(screen.getByTestId("toggle-dnc-1"));
    await waitFor(() =>
      expect(updateContact).toHaveBeenCalledWith(1, { do_not_contact: true }));
  });

  it("删除需行内二次确认：首点仅武装，再点才调接口", async () => {
    vi.mocked(fetchContacts).mockResolvedValue([contactFixture()]);
    vi.mocked(deleteContact).mockResolvedValue(undefined);
    render(ContactsPanel, { props: { companyId: 10 } });
    await screen.findByTestId("contact-row-1");
    await fireEvent.click(screen.getByTestId("delete-contact-1"));
    expect(deleteContact).not.toHaveBeenCalled();  // 首点只武装
    expect(screen.getByText("确认删除？")).toBeTruthy();
    await fireEvent.click(screen.getByTestId("delete-contact-1"));
    await waitFor(() => expect(deleteContact).toHaveBeenCalledWith(1));
  });

  it("接口失败显示错误信息", async () => {
    vi.mocked(fetchContacts).mockRejectedValue(new Error("boom"));
    render(ContactsPanel, { props: { companyId: 10 } });
    await screen.findByTestId("contacts-error");
    expect(screen.getByTestId("contacts-error").textContent).toContain("boom");
  });
});
