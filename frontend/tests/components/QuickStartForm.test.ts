/** 组件测试：快速建产品表单的校验、提交与错误态（不打真实后端）。 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { afterEach, describe, expect, it, vi } from "vitest";
import QuickStartForm from "@/features/products/components/QuickStartForm.vue";
import { createProduct, type Product } from "@/api/products";

vi.mock("@/api/products", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/products")>();
  return { ...actual, createProduct: vi.fn() };
});

const createdProduct: Product = {
  product_id: 9,
  code: "QUICK-0001",
  name: "女士棉质长裤",
  description: "",
  buyer_type: "importer",
  hs_codes: [{ hs_code: "620462", audience: "importer", note: "" }],
  counts: { potential: 2 },
  counts_by_audience: {},
};

function fill(label: string, value: string) {
  fireEvent.update(screen.getByLabelText(label), value);
}

afterEach(() => {
  cleanup();
  vi.mocked(createProduct).mockReset();
});

describe("QuickStartForm 校验", () => {
  it("名称为空提交显示错误且不调 API", async () => {
    const { emitted } = render(QuickStartForm);
    fill("HS 税号", "620462");
    fireEvent.click(screen.getByRole("button", { name: "找客户" }));
    expect(await screen.findByText("请填写产品名称"));
    expect(createProduct).not.toHaveBeenCalled();
    expect(emitted().created).toBeUndefined();
  });

  it("税号格式非法提交显示错误", async () => {
    render(QuickStartForm);
    fill("产品名称", "女士棉质长裤");
    fill("HS 税号", "62x462");
    fireEvent.click(screen.getByRole("button", { name: "找客户" }));
    expect(await screen.findByText(/税号需为 6-10 位数字/));
    expect(createProduct).not.toHaveBeenCalled();
  });

  it("前 6 位全零的税号本地即拒，不落到后端 422（对齐 is_valid_hs）", async () => {
    render(QuickStartForm);
    fill("产品名称", "女士棉质长裤");
    fill("HS 税号", "0000001"); // 7 位、前 6 位全零：旧规则 /^0+$/ 放行 → API 422
    fireEvent.click(screen.getByRole("button", { name: "找客户" }));
    expect(await screen.findByText(/不能全零/));
    expect(createProduct).not.toHaveBeenCalled();
  });
});

describe("QuickStartForm 提交", () => {
  it("合法填写调用 createProduct 并 emit created", async () => {
    vi.mocked(createProduct).mockResolvedValue(createdProduct);
    const { emitted } = render(QuickStartForm);
    fill("产品名称", "女士棉质长裤");
    fill("HS 税号", "620462");
    fill("买家行业词（选填）", "APPAREL; CLOTHING");
    fireEvent.click(screen.getByRole("button", { name: "找客户" }));
    await waitFor(() => expect(emitted().created).toBeTruthy());
    expect(createProduct).toHaveBeenCalledWith({
      name: "女士棉质长裤",
      hs_code: "620462",
      buyer_type: "importer",
      description: "",
      buyer_keywords: ["APPAREL", "CLOTHING"],
      peer_keywords: [],
    });
    expect(emitted().created[0]).toEqual([createdProduct]);
  });

  it("买家词留空提交则不传词（后端按受众给默认词）", async () => {
    vi.mocked(createProduct).mockResolvedValue(createdProduct);
    render(QuickStartForm);
    fill("产品名称", "瓦楞纸板");
    fill("HS 税号", "480810");
    fireEvent.update(screen.getByLabelText("卖给谁"), "factory");
    fireEvent.click(screen.getByRole("button", { name: "找客户" }));
    await waitFor(() =>
      expect(createProduct).toHaveBeenCalledWith(
        expect.objectContaining({ buyer_type: "factory", buyer_keywords: [] }),
      ),
    );
  });

  it("API 失败显示错误不 emit", async () => {
    vi.mocked(createProduct).mockRejectedValue(new Error("后端不可用"));
    const { emitted } = render(QuickStartForm);
    fill("产品名称", "女士棉质长裤");
    fill("HS 税号", "620462");
    fireEvent.click(screen.getByRole("button", { name: "找客户" }));
    expect(await screen.findByText(/创建失败：后端不可用/));
    expect(emitted().created).toBeUndefined();
  });
});
