/** 买家列表加载：带请求序号，过期响应不覆盖新响应（逐字符搜索会并发多个请求）。 */

import { ref } from "vue";
import { BUYERS_PAGE_LIMIT, fetchBuyers, type BuyerList } from "@/api/products";
import type { FilterState } from "./useBuyerFilters";

export function useBuyerList(
  productId: () => number,
  audience: () => string,
  filters: () => FilterState,
) {
  const result = ref<BuyerList | null>(null);
  const loading = ref(false);
  const error = ref("");
  let requestSeq = 0;

  async function load() {
    const seq = ++requestSeq;
    loading.value = true;
    error.value = "";
    const f = filters();
    try {
      const data = await fetchBuyers(productId(), {
        audience: audience(),
        tier: f.tier,
        q: f.q,
        country: f.country,
        minShipments: f.minShipments,
        order: f.order,
        limit: BUYERS_PAGE_LIMIT,
      });
      if (seq === requestSeq) result.value = data;
    } catch (e) {
      if (seq === requestSeq) error.value = `加载买家失败：${(e as Error).message}`;
    } finally {
      if (seq === requestSeq) loading.value = false;
    }
  }

  function reset() {
    result.value = null;
  }

  return { result, loading, error, load, reset };
}
