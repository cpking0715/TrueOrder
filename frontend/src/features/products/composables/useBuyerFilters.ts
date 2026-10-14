/** 买家筛选：纯函数构造查询参数与导出地址，便于直测。 */

import { computed, ref } from "vue";
import { withApiToken } from "@/api/client";
import { buildBuyersParams, type Tier, type Order } from "@/api/products";

export interface FilterState {
  tier: Tier;
  q: string;
  country: string;
  minShipments?: number;
  order: Order;
}

export function defaultFilters(tier: Tier = "potential"): FilterState {
  return { tier, q: "", country: "", minShipments: undefined, order: "shipments" };
}

export function filterQueryParams(state: FilterState, audience: string): Record<string, string> {
  return buildBuyersParams({
    audience,
    tier: state.tier,
    q: state.q,
    country: state.country,
    minShipments: state.minShipments,
    order: state.order,
  });
}

export function filterExportUrl(productId: number, state: FilterState, audience: string): string {
  const search = new URLSearchParams(filterQueryParams(state, audience)).toString();
  return withApiToken(`/api/products/${productId}/buyers/export.csv?${search}`);
}

export function useBuyerFilters(
  productId: () => number,
  audience: () => string,
  initialTier: Tier = "potential",
) {
  const state = ref<FilterState>(defaultFilters(initialTier));

  const params = computed(() => filterQueryParams(state.value, audience()));
  const exportUrl = computed(() => filterExportUrl(productId(), state.value, audience()));
  const search = computed(() => new URLSearchParams(params.value).toString());

  return { state, params, exportUrl, search };
}
