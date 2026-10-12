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

const COLUMNS: Stage[] = [
  "lead", "contacted", "replied", "sample_quote", "negotiating", "won_intent",
];
const INTENT_LABEL: Record<string, string> = { cold: "冷", warm: "温", hot: "热" };

const products = ref<Product[]>([]);
const productId = ref<number | null>(null);
const opportunities = ref<Opportunity[]>([]);
const error = ref("");
const busyId = ref<number | null>(null);
const lostReasonFor = ref<number | null>(null);
const lostReason = ref("");

const dueToday = computed(() =>
  opportunities.value.filter((o) => o.next_follow_up_on && o.next_follow_up_on <= todayIso()),
);

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

async function changeStage(opp: Opportunity, stage: Stage) {
  if (stage === "lost") {
    lostReasonFor.value = opp.opportunity_id;
    lostReason.value = "";
    return;
  }
  lostReasonFor.value = null;
  busyId.value = opp.opportunity_id;
  try {
    await patchOpportunity(opp.opportunity_id, { stage });
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busyId.value = null;
  }
}

async function confirmLost(opp: Opportunity) {
  if (!lostReason.value.trim()) {
    error.value = "流失必须填写原因";
    return;
  }
  busyId.value = opp.opportunity_id;
  try {
    await patchOpportunity(opp.opportunity_id, {
      stage: "lost",
      closed_reason: lostReason.value.trim(),
    });
    lostReasonFor.value = null;
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

onMounted(async () => {
  products.value = await fetchProducts();
  await reload();
});
</script>

<template>
  <div class="panel">
    <p class="eyebrow">
      Pipeline
    </p>
    <h1>跟进看板</h1>
    <div class="filterbar">
      <select
        v-model.number="productId"
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

    <div
      v-if="dueToday.length"
      class="alert"
      data-testid="due-today"
    >
      <strong>今日待跟进（{{ dueToday.length }}）</strong>
      <span
        v-for="o in dueToday"
        :key="o.opportunity_id"
        class="badge warn"
      >
        {{ o.company_name }}（{{ STAGE_LABEL[o.stage as Stage] }}）
      </span>
    </div>

    <div class="board">
      <div
        v-for="col in COLUMNS"
        :key="col"
        class="board-col"
        :data-testid="`col-${col}`"
      >
        <h3>{{ STAGE_LABEL[col] }}（{{ byStage(col).length }}）</h3>
        <div
          v-for="opp in byStage(col)"
          :key="opp.opportunity_id"
          class="board-card"
        >
          <strong>{{ opp.company_name }}</strong>
          <span class="badge">{{ INTENT_LABEL[opp.intent] }}</span>
          <div class="small muted code">
            {{ opp.next_follow_up_on ?? "未排期" }}
          </div>
          <p
            v-if="opp.owner_note"
            class="small muted"
          >
            {{ opp.owner_note }}
          </p>
          <select
            :value="opp.stage"
            :disabled="busyId === opp.opportunity_id"
            :data-testid="`stage-${opp.opportunity_id}`"
            @change="changeStage(opp, ($event.target as HTMLSelectElement).value as Stage)"
          >
            <option
              v-for="(label, s) in STAGE_LABEL"
              :key="s"
              :value="s"
            >
              {{ label }}
            </option>
          </select>
          <template v-if="lostReasonFor === opp.opportunity_id">
            <input
              v-model="lostReason"
              placeholder="流失原因（必填）"
              data-testid="lost-reason"
            >
            <button
              class="small"
              @click="confirmLost(opp)"
            >
              确认流失
            </button>
          </template>
        </div>
      </div>
    </div>

    <div
      v-if="opportunities.some((o) => o.stage === 'lost')"
      class="panel lost-panel"
    >
      <h3>已流失</h3>
      <p
        v-for="o in opportunities.filter((x) => x.stage === 'lost')"
        :key="o.opportunity_id"
        class="small muted"
      >
        {{ o.company_name }}：{{ o.closed_reason }}
        <button
          class="small ghost"
          @click="changeStage(o, 'lead')"
        >
          重新打开
        </button>
      </p>
    </div>
  </div>
</template>

<style scoped>
.board {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  align-items: start;
}
.board-col {
  background: #f4f7f8;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px;
}
.board-col h3 {
  margin: 0 0 8px;
}
.board-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.board-card select {
  font-size: 12px;
}
.lost-panel {
  margin-top: 12px;
}
@media (max-width: 720px) {
  .board { grid-template-columns: 1fr; }
}
</style>
