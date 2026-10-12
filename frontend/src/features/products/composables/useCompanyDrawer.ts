/** 公司抽屉取数：竞态守卫 + 按受众选得分，与组件生命周期解耦。 */

import { computed, ref, watch } from "vue";
import { fetchCompany, type CompanyDetail } from "@/api/products";

export function useCompanyDrawer(
  companyId: () => number | null,
  productId: () => number,
  audience: () => string | undefined,
) {
  const detail = ref<CompanyDetail | null>(null);
  const loading = ref(false);
  const error = ref("");

  // 关闭后/切换公司在途的旧响应不允许写入（与买家列表的 requestSeq 同口径）
  let requestSeq = 0;

  async function load(id: number) {
    const seq = ++requestSeq;
    loading.value = true;
    error.value = "";
    try {
      const data = await fetchCompany(id, productId(), audience());
      if (seq !== requestSeq) return;
      detail.value = data;
    } catch (e) {
      if (seq !== requestSeq) return;
      error.value = (e as Error).message;
    } finally {
      if (seq === requestSeq) {
        loading.value = false;
      }
    }
  }

  function reload() {
    if (companyId() != null) void load(companyId() as number);
  }

  // both 产品两类受众的得分不串台：抽屉只展示当前受众
  const score = computed(() => {
    if (!detail.value) return null;
    const byProduct = detail.value.scores.filter(
      (s) => s.product_id === productId(),
    );
    return (
      byProduct.find((s) => !audience() || s.audience === audience())
      ?? byProduct[0]
      ?? detail.value.scores[0]
      ?? null
    );
  });

  watch(
    () => [companyId(), productId(), audience()] as const,
    ([id]) => {
      if (id == null) {
        detail.value = null;
        return;
      }
      void load(id);
    },
    { immediate: true },
  );

  return { detail, loading, error, score, reload };
}
