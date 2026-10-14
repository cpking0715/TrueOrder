/** 跟进看板状态与动作：加载、推进阶段、流失（必填原因）、重开。 */

import { computed, ref } from "vue";
import { fetchOpportunities, patchOpportunity, type Opportunity, type Stage } from "@/api/opportunities";

export const COLUMNS: Stage[] = ["lead", "contacted", "replied", "sample_quote", "negotiating", "won_intent"];
export const NEXT_STAGE: Partial<Record<Stage, Stage>> = {
  lead: "contacted",
  contacted: "replied",
  replied: "sample_quote",
  sample_quote: "negotiating",
  negotiating: "won_intent",
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function usePipeline() {
  const productId = ref<number | null>(null);
  const opportunities = ref<Opportunity[]>([]);
  const error = ref("");
  const busyId = ref<number | null>(null);
  const lostTarget = ref<Opportunity | null>(null);

  const dueToday = computed(() =>
    opportunities.value.filter(
      (o) => o.next_follow_up_on && o.next_follow_up_on <= todayIso()
        && o.stage !== "lost" && o.stage !== "won_intent",
    ),
  );
  const lostList = computed(() => opportunities.value.filter((o) => o.stage === "lost"));

  async function reload() {
    try {
      opportunities.value = await fetchOpportunities(
        productId.value ? { product_id: productId.value } : undefined,
      );
      error.value = "";
    } catch (e) {
      error.value = `加载商机失败：${(e as Error).message}`;
    }
  }

  async function patch(opp: Opportunity, body: Parameters<typeof patchOpportunity>[1]): Promise<boolean> {
    busyId.value = opp.opportunity_id;
    try {
      await patchOpportunity(opp.opportunity_id, body);
      await reload();
      return true;
    } catch (e) {
      error.value = (e as Error).message;
      return false;
    } finally {
      busyId.value = null;
    }
  }

  async function advance(opp: Opportunity) {
    const next = NEXT_STAGE[opp.stage as Stage];
    if (next) await patch(opp, { stage: next });
  }

  async function confirmLost(reason: string) {
    const target = lostTarget.value;
    if (!target || !reason.trim()) return;
    if (await patch(target, { stage: "lost", closed_reason: reason.trim() })) {
      lostTarget.value = null;
    }
  }

  const reopen = (opp: Opportunity) => patch(opp, { stage: "lead" });
  const byStage = (stage: Stage) => opportunities.value.filter((o) => o.stage === stage);

  return {
    productId, opportunities, error, busyId, lostTarget, dueToday, lostList,
    reload, advance, confirmLost, reopen, byStage,
  };
}
