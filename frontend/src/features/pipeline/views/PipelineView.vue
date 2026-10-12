<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  STAGE_LABEL,
  fetchOpportunities,
  patchOpportunity,
  type Opportunity,
  type Stage,
} from "@/api/opportunities";
import { fetchProducts, type Product } from "@/api/products";
import BoardCard from "../components/BoardCard.vue";

const COLUMNS: Stage[] = [
  "lead", "contacted", "replied", "sample_quote", "negotiating", "won_intent",
];
const NEXT_STAGE: Partial<Record<Stage, Stage>> = {
  lead: "contacted", contacted: "replied", replied: "sample_quote",
  sample_quote: "negotiating", negotiating: "won_intent",
};
const INTENT_CLASS: Record<string, string> = { cold: "muted", warm: "potential", hot: "precise" };
const INTENT_LABEL: Record<string, string> = { cold: "冷", warm: "温", hot: "热" };

const products = ref<Product[]>([]);
const productId = ref<number | null>(null);
const opportunities = ref<Opportunity[]>([]);
const error = ref("");
const busyId = ref<number | null>(null);
const lostTarget = ref<Opportunity | null>(null);
const lostReason = ref("");

const dueToday = computed(() =>
  opportunities.value.filter(
    (o) => o.next_follow_up_on && o.next_follow_up_on <= todayIso()
      && o.stage !== "lost" && o.stage !== "won_intent",
  ),
);
const lostList = computed(() => opportunities.value.filter((o) => o.stage === "lost"));

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

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

async function advance(opp: Opportunity) {
  const next = NEXT_STAGE[opp.stage as Stage];
  if (!next) return;
  busyId.value = opp.opportunity_id;
  try {
    await patchOpportunity(opp.opportunity_id, { stage: next });
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busyId.value = null;
  }
}

function askLost(opp: Opportunity) {
  lostTarget.value = opp;
  lostReason.value = "";
}

async function confirmLost() {
  if (!lostTarget.value || !lostReason.value.trim()) return;
  busyId.value = lostTarget.value.opportunity_id;
  try {
    await patchOpportunity(lostTarget.value.opportunity_id, {
      stage: "lost",
      closed_reason: lostReason.value.trim(),
    });
    lostTarget.value = null;
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busyId.value = null;
  }
}

async function reopen(opp: Opportunity) {
  busyId.value = opp.opportunity_id;
  try {
    await patchOpportunity(opp.opportunity_id, { stage: "lead" });
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busyId.value = null;
  }
}

function byStage(stage: Stage): Opportunity[] {
  return opportunities.value.filter((o) => o.stage === stage);
}

function intentBadge(intent: string): string {
  return `badge ${INTENT_CLASS[intent] ?? "muted"}`;
}

onMounted(async () => {
  products.value = await fetchProducts();
  await reload();
});
</script>

<template>
  <div class="pipeline-page">
    <!-- 功能区 1：标题与筛选 -->
    <div class="panel pipeline-header">
      <div>
        <p class="eyebrow">
          Pipeline
        </p>
        <h1>跟进看板</h1>
      </div>
      <select
        v-model.number="productId"
        class="pipeline-filter"
        @change="reload"
      >
        <option :value="null">
          全部产品
        </option>
        <option
          v-for="p in products"
          :key="p.product_id"
          :value="p.product_id"
        >
          {{ p.name }}
        </option>
      </select>
    </div>

    <p
      v-if="error"
      class="error small"
      role="alert"
    >
      {{ error }}
    </p>

    <!-- 功能区 2：今日待跟进（有内容才显示） -->
    <div
      v-if="dueToday.length"
      class="panel due-panel"
      data-testid="due-today"
    >
      <span class="badge excluded">今日待跟进 {{ dueToday.length }}</span>
      <div
        v-for="o in dueToday"
        :key="o.opportunity_id"
        class="due-chip"
      >
        <strong>{{ o.company_name }}</strong>
        <span class="muted small">{{ STAGE_LABEL[o.stage as Stage] }} · {{ o.next_follow_up_on }}</span>
      </div>
    </div>

    <!-- 功能区 3：六列看板 -->
    <div class="board">
      <div
        v-for="col in COLUMNS"
        :key="col"
        class="board-col"
        :data-testid="`col-${col}`"
      >
        <h3>{{ STAGE_LABEL[col] }}<span class="count">{{ byStage(col).length }}</span></h3>
        <BoardCard
          v-for="opp in byStage(col)"
          :key="opp.opportunity_id"
          :opp="opp"
          :busy="busyId === opp.opportunity_id"
          :show-advance="NEXT_STAGE[opp.stage as Stage] != null"
          :show-lost="opp.stage !== 'won_intent'"
          :intent-badge="intentBadge(opp.intent)"
          :intent-label="INTENT_LABEL[opp.intent] ?? opp.intent"
          @advance="advance(opp)"
          @lost="askLost(opp)"
        />
        <p
          v-if="!byStage(col).length"
          class="board-empty small muted"
        >
          —
        </p>
      </div>
    </div>

    <!-- 流失原因内联（覆盖在页面底部，不挡看板） -->
    <div
      v-if="lostTarget"
      class="panel lost-form"
      data-testid="lost-form"
    >
      <span>流失 <strong>{{ lostTarget.company_name }}</strong>，原因：</span>
      <input
        v-model="lostReason"
        placeholder="必填"
        data-testid="lost-reason"
        @keydown.enter.prevent="confirmLost"
      >
      <button
        class="small primary"
        :disabled="!lostReason.trim() || busyId != null"
        @click="confirmLost"
      >
        确认流失
      </button>
      <button
        class="small ghost"
        @click="lostTarget = null"
      >
        取消
      </button>
    </div>

    <!-- 功能区 4：已流失（紧凑条） -->
    <div
      v-if="lostList.length"
      class="panel lost-strip"
    >
      <h3>已流失</h3>
      <span
        v-for="o in lostList"
        :key="o.opportunity_id"
        class="lost-chip"
        :title="o.closed_reason ?? ''"
        :data-testid="`lost-${o.opportunity_id}`"
      >
        {{ o.company_name }}：{{ (o.closed_reason ?? "").slice(0, 20) }}
        <button
          class="small ghost"
          :disabled="busyId === o.opportunity_id"
          @click="reopen(o)"
        >
          重开
        </button>
      </span>
    </div>
  </div>
</template>

<style scoped>
.pipeline-page { display: flex; flex-direction: column; gap: 12px; }
.pipeline-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 18px; }
.pipeline-header h1 { margin: 0; }
.pipeline-filter { min-width: 200px; }

.due-panel { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 18px; }
.due-chip { display: flex; flex-direction: column; padding: 4px 10px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }

.board { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; align-items: start; }
.board-col { background: #f0f4f5; border: 1px solid var(--line); border-radius: 8px; padding: 8px; min-height: 120px; }
.board-col h3 { margin: 0 0 8px; font-size: 12px; display: flex; align-items: center; gap: 6px; color: var(--ink-soft); }
.board-col .count { background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 0 7px; font-size: 11px; }
.board-empty { text-align: center; padding: 20px 0; }

.lost-form { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; border-left: 3px solid var(--stamp); padding: 10px 18px; }
.lost-strip { padding: 10px 18px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.lost-strip h3 { margin: 0; font-size: 12px; color: var(--ink-soft); }
.lost-chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border: 1px dashed var(--line); border-radius: 6px; font-size: 12px; color: var(--ink-soft); }

@media (max-width: 1100px) { .board { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 720px) { .board { grid-template-columns: repeat(2, 1fr); } .pipeline-header { flex-direction: column; align-items: stretch; } }
</style>
