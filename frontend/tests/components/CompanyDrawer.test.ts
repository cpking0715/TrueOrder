/** 组件测试：公司抽屉的 Esc 关闭与在途响应丢弃（不打真实后端）。 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import CompanyDrawer from "@/features/products/components/CompanyDrawer.vue";
import { fetchCompany, type CompanyDetail } from "@/api/products";

vi.mock("@/api/products", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/products")>();
  return { ...actual, fetchCompany: vi.fn() };
});

function companyFixture(id: number, name: string): CompanyDetail {
  return {
    company: {
      company_id: id,
      name,
      name_variants: [name],
      normalized_name: name,
      country: "US",
      city: "NEW YORK",
      address: "",
      website: null,
      website_confirmed: false,
      website_source: "",
      website_confidence: "",
      same_name_conflict: false,
    },
    scores: [],
    bills: [],
    bills_truncated: false,
  };
}

afterEach(() => {
  cleanup();
  vi.mocked(fetchCompany).mockReset();
});

describe("CompanyDrawer 关闭交互", () => {
  it("抽屉打开时按 Esc 发出 close", async () => {
    vi.mocked(fetchCompany).mockResolvedValue(companyFixture(1, "AAA LLC"));
    const { emitted } = render(CompanyDrawer, {
      props: { companyId: 1, productId: 1 },
    });
    await screen.findByTestId("company-drawer");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(emitted().close).toBeTruthy();
  });

  it("抽屉未打开时按 Esc 不发 close", () => {
    const { emitted } = render(CompanyDrawer, { props: { companyId: null, productId: 1 } });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(emitted().close).toBeUndefined();
  });
});

describe("CompanyDrawer 在途响应竞态（F4 复审）", () => {
  it("先开 A（慢）→ 关 → 开 B（快），A 迟到不得覆盖 B", async () => {
    let releaseA: (() => void) | undefined;
    vi.mocked(fetchCompany).mockImplementation(async (id) => {
      if (id === 1) {
        await new Promise<void>((resolve) => {
          releaseA = resolve;
        });
        return companyFixture(1, "AAA LLC");
      }
      return companyFixture(2, "BBB LLC");
    });

    const { rerender } = render(CompanyDrawer, {
      props: { companyId: 1, productId: 1 },
    });
    await waitFor(() => expect(fetchCompany).toHaveBeenCalledWith(1, 1, undefined));

    // 关闭后立刻打开 B
    await rerender({ companyId: null, productId: 1 });
    await rerender({ companyId: 2, productId: 1 });
    expect(await screen.findByText("BBB LLC")).toBeTruthy();

    // A 的响应此刻才返回：不允许覆盖 B
    releaseA?.();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.getByTestId("company-drawer").textContent).toContain("BBB LLC");
    expect(screen.queryByText("AAA LLC")).toBeNull();
  });
});
