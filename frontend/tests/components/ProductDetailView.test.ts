/** 组件测试：注入假 api 模块，断言用户可见结果，不打真实后端。 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { createMemoryHistory, createRouter } from "vue-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ProductDetailView from "@/features/products/views/ProductDetailView.vue";
import {
  fetchBuyers,
  fetchCompany,
  fetchMeta,
  fetchProducts,
  type Buyer,
  type BuyerList,
  type CompanyDetail,
  type Product,
} from "@/api/products";

vi.mock("@/api/products", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/products")>();
  return {
    ...actual,
    fetchMeta: vi.fn(),
    fetchProducts: vi.fn(),
    fetchBuyers: vi.fn(),
    fetchCompany: vi.fn(),
  };
});

const productFixture: Product = {
  product_id: 1,
  code: "P-GARMENT",
  name: "女士棉质长裤（成衣）",
  description: "卖给海外进口商",
  buyer_type: "importer",
  hs_codes: [{ hs_code: "620462", audience: "importer", note: "成衣税号" }],
  counts: { potential: 2, precise: 1, excluded: 6 },
  counts_by_audience: {},
};

const buyersByTier: Record<string, Buyer[]> = {
  potential: [
    {
      company_id: 11,
      name: "LONE STAR CLOTHING CO",
      country: "US",
      city: "AUSTIN",
      same_name_conflict: false,
      tier: "potential",
      exclusion_code: null,
      shipments: 1,
      last_arrival: "2025-03-15",
      suppliers: ["NINGBO WEAR CO LTD"],
      reasons: [{ code: "RECENT_24M", text: "近 24 个月自中国/越南进口该税号 1 票", bill_ids: [501] }],
    },
  ],
  precise: [
    {
      company_id: 10,
      name: "BROOKLYN APPAREL LLC",
      country: "US",
      city: "NEW YORK",
      same_name_conflict: false,
      tier: "precise",
      exclusion_code: null,
      shipments: 3,
      last_arrival: "2026-09-01",
      suppliers: ["HANGZHOU GARMENT CO LTD"],
      reasons: [
        { code: "RECENT_24M", text: "近 24 个月自中国/越南进口该税号 3 票", bill_ids: [1, 2, 3] },
        { code: "SUPPLIER_MATCH", text: "近 12 个月由 HANGZHOU GARMENT 稳定供货 3 票", bill_ids: [1, 2, 3] },
      ],
    },
  ],
  excluded: [],
};

const companyFixture: CompanyDetail = {
  company: {
    company_id: 10,
    name: "BROOKLYN APPAREL LLC",
    name_variants: ["BROOKLYN APPAREL LLC"],
    normalized_name: "BROOKLYN APPAREL",
    country: "US",
    city: "NEW YORK",
    address: "350 FIFTH AVE",
    website: null,
    website_confirmed: false,
    same_name_conflict: false,
  },
  scores: [
    {
      product_id: 1,
      audience: "importer",
      tier: "precise",
      exclusion_code: null,
      reasons: [
        { code: "SUPPLIER_MATCH", text: "近 12 个月由 HANGZHOU GARMENT 稳定供货 3 票", bill_ids: [1, 2, 3] },
      ],
      shipments: 3,
      last_arrival: "2026-09-01",
      suppliers: ["HANGZHOU GARMENT CO LTD"],
    },
  ],
  bills: [
    {
      bill_id: 1,
      arrival_date: "2026-02-10",
      hs_code: "620462",
      hs_suspect: false,
      origin_country: "CN",
      shipper: "HANGZHOU GARMENT CO LTD",
      consignee: "BROOKLYN APPAREL LLC",
      role: "consignee",
      product_description: "WOMENS COTTON TROUSERS",
      port: "NEW YORK",
      bill_number: "BOL-1001",
      quantity: "1200 CTNS",
    },
  ],
  bills_truncated: false,
};

function listFixture(tier: Buyer["tier"] | undefined, total: number): BuyerList {
  return { items: buyersByTier[tier ?? "potential"] ?? [], total, audience: "importer", tier: tier ?? null, q: null };
}

async function renderView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div>list</div>" } },
      { path: "/products/:id", component: ProductDetailView },
    ],
  });
  router.push("/products/1");
  await router.isReady();
  return render(ProductDetailView, { global: { plugins: [router] } });
}

async function renderViewWithRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div>list</div>" } },
      { path: "/products/:id", component: ProductDetailView },
    ],
  });
  router.push("/products/1");
  await router.isReady();
  render(ProductDetailView, { global: { plugins: [router] } });
  return router;
}

beforeEach(() => {
  vi.mocked(fetchMeta).mockResolvedValue({
    sample_mode: true,
    sample_notice: "当前库内为公开样本数据（非全量样本）。",
  });
  vi.mocked(fetchProducts).mockResolvedValue([productFixture]);
  vi.mocked(fetchBuyers).mockImplementation(async (_id, query) =>
    listFixture(query.tier, (buyersByTier[query.tier ?? "potential"] ?? []).length),
  );
  vi.mocked(fetchCompany).mockResolvedValue(companyFixture);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("产品详情页（用户可见结果）", () => {
  it("显示产品信息、非全量声明和三个页签计数", async () => {
    await renderView();
    expect(await screen.findByText("女士棉质长裤（成衣）")).toBeTruthy();
    expect(screen.getByText(/非全量样本/)).toBeTruthy();
    expect(screen.getByTestId("tab-potential").textContent).toContain("2");
    expect(screen.getByTestId("tab-precise").textContent).toContain("1");
    expect(screen.getByTestId("tab-excluded").textContent).toContain("6");
  });

  it("默认展示潜在客户", async () => {
    await renderView();
    expect(await screen.findByText("LONE STAR CLOTHING CO")).toBeTruthy();
    // F4 防线：列表必须显式带大 limit，否则后端默认 50 会让「所见」与「导出」不一致
    expect(fetchBuyers).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ tier: "potential", limit: 500 }),
    );
  });

  it("点击精准页签切换到精准客户", async () => {
    await renderView();
    await screen.findByText("LONE STAR CLOTHING CO");
    await fireEvent.click(screen.getByTestId("tab-precise"));
    expect(await screen.findByText("BROOKLYN APPAREL LLC")).toBeTruthy();
    expect(screen.queryByText("LONE STAR CLOTHING CO")).toBeNull();
  });

  it("排除页签为空时显示空态", async () => {
    await renderView();
    await screen.findByText("女士棉质长裤（成衣）");
    await fireEvent.click(screen.getByTestId("tab-excluded"));
    expect(await screen.findByTestId("buyers-empty")).toBeTruthy();
  });

  it("计数全为 0 的产品显示导入提单指引", async () => {
    vi.mocked(fetchProducts).mockResolvedValue([
      { ...productFixture, name: "新产品", counts: {}, counts_by_audience: {} },
    ]);
    vi.mocked(fetchBuyers).mockResolvedValue({
      items: [], total: 0, audience: "importer", tier: null, q: null,
    });
    await renderView();
    const hint = await screen.findByTestId("no-bills-hint");
    expect(hint.textContent).toContain("库里还没有该税号的提单");
    expect(hint.textContent).toContain("导入提单");
  });

  it("计数非 0 的产品不显示导入指引", async () => {
    await renderView();
    await screen.findByText("女士棉质长裤（成衣）");
    expect(screen.queryByTestId("no-bills-hint")).toBeNull();
  });

  it("点击公司行打开抽屉：票数、最近到港、供货方、理由与提单", async () => {
    await renderView();
    await screen.findByText("女士棉质长裤（成衣）");
    await fireEvent.click(screen.getByTestId("tab-precise"));
    await fireEvent.click(await screen.findByText("BROOKLYN APPAREL LLC"));
    const drawer = await screen.findByTestId("company-drawer");
    expect(drawer.textContent).toContain("BROOKLYN APPAREL LLC");
    expect(drawer.textContent).toContain("3");
    expect(drawer.textContent).toContain("2026-09-01");
    expect(drawer.textContent).toContain("HANGZHOU GARMENT CO LTD");
    expect(screen.getAllByTestId("bill-chip").length).toBeGreaterThan(0);
    const billsTable = screen.getByTestId("drawer-bills");
    expect(billsTable.textContent).toContain("620462");
    expect(billsTable.textContent).toContain("BOL-1001"); // F1：提单号列可见
    await fireEvent.click(screen.getByTestId("drawer-close"));
    await waitFor(() => expect(screen.queryByTestId("company-drawer")).toBeNull());
  });

  it("点击理由里的提单号会高亮定位对应提单行（F1）", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    await renderView();
    await screen.findByText("女士棉质长裤（成衣）");
    await fireEvent.click(screen.getByTestId("tab-precise"));
    await fireEvent.click(await screen.findByText("BROOKLYN APPAREL LLC"));
    await screen.findByTestId("reason-list");
    await fireEvent.click(screen.getAllByTestId("bill-chip")[0]);
    await waitFor(() => {
      const highlighted = document.querySelector("tr.highlighted");
      expect(highlighted).toBeTruthy();
      expect(highlighted?.id).toMatch(/^bill-row-\d+$/);
      expect(scrollIntoView).toHaveBeenCalled();
    });
  });

  it("列表被截断时显示截断提示，导出语义为全部（F4）", async () => {
    vi.mocked(fetchBuyers).mockImplementation(async (_id, query) => ({
      items: buyersByTier[query.tier ?? "potential"] ?? [],
      total: 600,
      audience: "importer",
      tier: query.tier ?? null,
      q: null,
    }));
    await renderView();
    await screen.findByText("LONE STAR CLOTHING CO");
    const hint = await screen.findByTestId("truncated-hint");
    expect(hint.textContent).toContain("共 600 家");
    expect(hint.textContent).toContain("导出 CSV 含全部");
  });

  it("结果未截断时不显示截断提示（F4）", async () => {
    await renderView();
    await screen.findByText("LONE STAR CLOTHING CO");
    expect(screen.queryByTestId("truncated-hint")).toBeNull();
  });

  it("导出按钮指向当前筛选的导出端点", async () => {
    await renderView();
    await screen.findByText("女士棉质长裤（成衣）");
    await fireEvent.click(screen.getByTestId("tab-precise"));
    const link = screen.getByTestId("export-button") as HTMLAnchorElement;
    await waitFor(() => {
      expect(link.getAttribute("href")).toContain("tier=precise");
      expect(link.getAttribute("href")).toContain("audience=importer");
    });
  });

  it("搜索的过期响应不覆盖新响应（复现：逐字符输入竞态）", async () => {
    let releaseSlow: (() => void) | undefined;
    vi.mocked(fetchBuyers).mockImplementation(async (_id, query) => {
      if (query.q === "slow") {
        await new Promise<void>((resolve) => {
          releaseSlow = resolve;
        });
        return listFixture("potential", 99);
      }
      return listFixture(query.tier, (buyersByTier[query.tier ?? "potential"] ?? []).length);
    });

    await renderView();
    await screen.findByText("女士棉质长裤（成衣）");
    // 触发一个慢请求（旧搜索词），再触发一个快请求（新搜索词）
    await fireEvent.update(screen.getByTestId("filter-q"), "slow");
    await fireEvent.update(screen.getByTestId("filter-q"), "fast");
    expect(await screen.findByText("LONE STAR CLOTHING CO")).toBeTruthy();
    // 慢请求此刻才返回：不允许覆盖新结果
    releaseSlow?.();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.getByText("LONE STAR CLOTHING CO")).toBeTruthy();
    expect(screen.queryByText(/共 99 家/)).toBeNull();
  });

  it("路由在产品间切换时受众与列表跟随新产品（复现：纸板页不能残留成衣数据）", async () => {
    const boardProduct: Product = {
      product_id: 2,
      code: "P-BOARD",
      name: "瓦楞纸板（原纸）",
      description: "卖给纸壳厂",
      buyer_type: "factory",
      hs_codes: [{ hs_code: "480810", audience: "factory", note: "原料税号" }],
      counts: { potential: 2, precise: 2, excluded: 0 },
      counts_by_audience: {},
    };
    vi.mocked(fetchProducts).mockResolvedValue([productFixture, boardProduct]);
    vi.mocked(fetchBuyers).mockImplementation(async (id, query) => {
      if (id === 2) {
        return {
          items: [
            {
              company_id: 30,
              name: "GREAT LAKES PACKAGING CORP",
              country: "US",
              city: "TOLEDO",
              same_name_conflict: false,
              tier: "precise",
              exclusion_code: null,
              shipments: 3,
              last_arrival: "2026-07-20",
              suppliers: ["SHANDONG PAPER CO LTD"],
              reasons: [],
            },
          ],
          total: 1,
          audience: "factory",
          tier: query.tier ?? null,
          q: null,
        };
      }
      return listFixture(query.tier, (buyersByTier[query.tier ?? "potential"] ?? []).length);
    });

    const router = await renderViewWithRouter();
    await screen.findByText("女士棉质长裤（成衣）");
    await router.push("/products/2");
    expect(await screen.findByText("瓦楞纸板（原纸）")).toBeTruthy();
    expect(await screen.findByText("GREAT LAKES PACKAGING CORP")).toBeTruthy();
    expect(screen.queryByText("BROOKLYN APPAREL LLC")).toBeNull();
    expect(fetchBuyers).toHaveBeenCalledWith(2, expect.objectContaining({ audience: "factory" }));
  });

  it("both 产品页签计数按受众细分且抽屉请求带受众（F5）", async () => {
    const bothProduct: Product = {
      product_id: 5,
      code: "P-BOTH",
      name: "面料与成衣",
      description: "两者都卖",
      buyer_type: "both",
      hs_codes: [
        { hs_code: "620462", audience: "importer", note: "" },
        { hs_code: "600632", audience: "factory", note: "" },
      ],
      counts: { precise: 2 },
      counts_by_audience: { importer: { precise: 1 }, factory: { precise: 7 } },
    };
    vi.mocked(fetchProducts).mockResolvedValue([bothProduct]);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", component: { template: "<div>list</div>" } },
        { path: "/products/:id", component: ProductDetailView },
      ],
    });
    router.push("/products/5");
    await router.isReady();
    render(ProductDetailView, { global: { plugins: [router] } });

    // 默认进口商视角：页签计数用 importer 的细分（1），不是总和（2）
    await screen.findByText("面料与成衣");
    await waitFor(() => {
      expect(screen.getByTestId("tab-precise").textContent).toContain("1");
    });
    // 切到工厂视角：页签计数跟随 factory（7）
    await fireEvent.click(screen.getByText("工厂视角"));
    await waitFor(() => {
      expect(screen.getByTestId("tab-precise").textContent).toContain("7");
    });
    // 打开抽屉：请求携带当前受众
    const buyer: Buyer = {
      company_id: 77,
      name: "SAIGON WEAVING MILL JSC",
      country: "US",
      city: "",
      same_name_conflict: false,
      tier: "precise",
      exclusion_code: null,
      shipments: 2,
      last_arrival: "2026-06-15",
      suppliers: ["JIANGSU FABRIC CO LTD"],
      reasons: [],
    };
    vi.mocked(fetchBuyers).mockResolvedValue({
      items: [buyer],
      total: 1,
      audience: "factory",
      tier: "precise",
      q: null,
    });
    await fireEvent.update(screen.getByTestId("filter-q"), "x");
    await fireEvent.click(await screen.findByText("SAIGON WEAVING MILL JSC"));
    await waitFor(() => {
      expect(fetchCompany).toHaveBeenCalledWith(77, 5, "factory");
    });
  });
});
