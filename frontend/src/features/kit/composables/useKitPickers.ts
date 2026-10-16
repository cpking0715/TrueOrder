/** 开发信/询盘页共用：加载「有档案的产品」与线索库买家，供下拉选择。 */

import { computed, ref } from "vue";
import { fetchKitBuyers, fetchKitProfiles, type KitBuyer, type KitProfile } from "@/api/kit";

export function useKitPickers() {
  const products = ref<KitProfile[]>([]);
  const buyers = ref<KitBuyer[]>([]);
  const readyProducts = computed(() => products.value.filter((p) => p.has_profile));

  async function loadPickers() {
    const [p, b] = await Promise.all([fetchKitProfiles(), fetchKitBuyers()]);
    products.value = p;
    buyers.value = b;
  }

  return { products, buyers, readyProducts, loadPickers };
}
