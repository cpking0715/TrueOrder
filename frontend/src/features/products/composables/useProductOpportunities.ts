/** 产品详情的跟进商机：列表、按企业映射阶段、加入跟进。 */

import { computed, ref, type Ref } from "vue";
import { createOpportunity, fetchOpportunities, type Opportunity } from "@/api/opportunities";

export function useProductOpportunities(productId: () => number, selectedCompanyId: Ref<number | null>) {
  const opportunities = ref<Opportunity[]>([]);

  const followStages = computed(() =>
    Object.fromEntries(opportunities.value.map((o) => [o.company_id, o.stage])),
  );
  const selectedOpportunity = computed(
    () => opportunities.value.find((o) => o.company_id === selectedCompanyId.value) ?? null,
  );

  async function reload() {
    try {
      opportunities.value = await fetchOpportunities({ product_id: productId() });
    } catch {
      opportunities.value = [];
    }
  }

  /** 加入跟进；失败返回错误文案（由视图展示），成功返回空串。 */
  async function followUp(companyId: number): Promise<string> {
    try {
      await createOpportunity(productId(), companyId);
      await reload();
      return "";
    } catch (e) {
      return `加入跟进失败：${(e as Error).message}`;
    }
  }

  return { opportunities, followStages, selectedOpportunity, reload, followUp };
}
