/** 税号反查组件：关键词搜索 → 聚合列表 → 点选回填。fetch 走真实端点的相对路径（jsdom mock fetch）。 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import HsSuggest from "@/features/products/components/HsSuggest.vue";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubFetch(body: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok,
      json: async () => body,
      status: ok ? 200 : 422,
    }),
  );
}

describe("HsSuggest 税号反查", () => {
  it("搜索返回聚合列表（票数与样例描述可见）", async () => {
    stubFetch([
      { hs_code: "620462", shipments: 7, sample_description: "WOMENS COTTON TROUSERS" },
      { hs_code: "620442", shipments: 2, sample_description: "WOMEN TROUSERS COTTON" },
    ]);
    render(HsSuggest, { props: { initialKeyword: "女士棉裤" } });
    await fireEvent.click(screen.getByTestId("hs-suggest-open"));
    await fireEvent.update(screen.getByTestId("hs-suggest-keyword"), "COTTON TROUSERS");
    await fireEvent.click(screen.getByTestId("hs-suggest-search"));
    const list = await screen.findByTestId("hs-suggest-list");
    expect(list.textContent).toContain("620462");
    expect(list.textContent).toContain("7 票");
    expect(list.textContent).toContain("WOMENS COTTON TROUSERS");
  });

  it("点选后发出 pick 事件并收起", async () => {
    stubFetch([{ hs_code: "480810", shipments: 3, sample_description: "CORRUGATED PAPER" }]);
    const { emitted } = render(HsSuggest, { props: {} });
    await fireEvent.click(screen.getByTestId("hs-suggest-open"));
    await fireEvent.update(screen.getByTestId("hs-suggest-keyword"), "PAPERBOARD");
    await fireEvent.click(screen.getByTestId("hs-suggest-search"));
    await waitFor(() => screen.getByTestId("hs-pick-480810"));
    await fireEvent.click(screen.getByTestId("hs-pick-480810"));
    expect(emitted().pick).toEqual([["480810"]]);
    expect(screen.queryByTestId("hs-suggest")).toBeNull();
  });

  it("关键词太短提示", async () => {
    stubFetch([]);
    render(HsSuggest);
    await fireEvent.click(screen.getByTestId("hs-suggest-open"));
    await fireEvent.update(screen.getByTestId("hs-suggest-keyword"), "a");
    await fireEvent.click(screen.getByTestId("hs-suggest-search"));
    expect(await screen.findByText(/至少 2 个字符/)).toBeTruthy();
  });

  it("无结果给出换词指引", async () => {
    stubFetch([]);
    render(HsSuggest);
    await fireEvent.click(screen.getByTestId("hs-suggest-open"));
    await fireEvent.update(screen.getByTestId("hs-suggest-keyword"), "zzzz qqq");
    await fireEvent.click(screen.getByTestId("hs-suggest-search"));
    expect(await screen.findByTestId("hs-suggest-error")).toBeTruthy();
  });
});
