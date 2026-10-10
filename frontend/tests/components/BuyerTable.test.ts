/** 组件测试：买家表行可键盘操作（Enter/Space 打开抽屉，走 D4 可访问性防线）。 */

import { cleanup, fireEvent, render, screen } from "@testing-library/vue";
import { afterEach, describe, expect, it } from "vitest";
import BuyerTable from "@/features/products/components/BuyerTable.vue";
import type { Buyer } from "@/api/products";

const buyer: Buyer = {
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
  reasons: [],
};

afterEach(() => cleanup());

describe("BuyerTable 键盘可达性", () => {
  it("行可聚焦且 Enter/Space 触发选中", async () => {
    const { emitted } = render(BuyerTable, {
      props: { buyers: [buyer], loading: false },
    });
    const row = screen.getByRole("button", { name: /BROOKLYN APPAREL/ });
    await fireEvent.keyDown(row, { key: "Enter" });
    expect(emitted().select).toBeTruthy();
    await fireEvent.keyDown(row, { key: " " });
    expect(emitted().select).toHaveLength(2);
    // 点击同样有效
    await fireEvent.click(row);
    expect(emitted().select).toHaveLength(3);
  });
});
