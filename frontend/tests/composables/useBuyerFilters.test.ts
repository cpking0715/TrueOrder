import { describe, expect, it } from "vitest";
import {
  defaultFilters,
  filterExportUrl,
  filterQueryParams,
} from "@/features/products/composables/useBuyerFilters";

describe("买家筛选参数构造", () => {
  it("tier 与受众总是传入", () => {
    const params = filterQueryParams(defaultFilters("precise"), "importer");
    expect(params).toEqual({ tier: "precise", audience: "importer", order: "shipments" });
  });

  it("空搜索与空国家不产生参数", () => {
    const state = defaultFilters("potential");
    state.q = "  ";
    state.country = "";
    const params = filterQueryParams(state, "factory");
    expect(params).not.toHaveProperty("q");
    expect(params).not.toHaveProperty("country");
  });

  it("搜索词、国家、最少票数进入参数", () => {
    const state = defaultFilters("precise");
    state.q = "packaging OR apparel";
    state.country = "us";
    state.minShipments = 3;
    const params = filterQueryParams(state, "factory");
    expect(params.q).toBe("packaging OR apparel");
    expect(params.country).toBe("US");
    expect(params.min_shipments).toBe("3");
  });

  it("minShipments 为 1 时省略（等价于不限）", () => {
    const state = defaultFilters("precise");
    state.minShipments = 1;
    expect(filterQueryParams(state, "importer")).not.toHaveProperty("min_shipments");
  });
});

describe("导出地址", () => {
  it("包含当前筛选与导出端点", () => {
    const state = defaultFilters("precise");
    state.q = "apparel";
    state.minShipments = 2;
    const url = filterExportUrl(7, state, "importer");
    expect(url.startsWith("/api/products/7/buyers/export.csv?")).toBe(true);
    expect(url).toContain("tier=precise");
    expect(url).toContain("audience=importer");
    expect(url).toContain("q=apparel");
    expect(url).toContain("min_shipments=2");
  });

  it("切换页签后导出地址跟随", () => {
    const state = defaultFilters("potential");
    const before = filterExportUrl(1, state, "factory");
    state.tier = "excluded";
    const after = filterExportUrl(1, state, "factory");
    expect(before).toContain("tier=potential");
    expect(after).toContain("tier=excluded");
  });
});
