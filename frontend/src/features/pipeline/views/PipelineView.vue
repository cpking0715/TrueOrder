<script setup lang="ts">
import { onMounted, ref } from "vue";
import OutreachPanel from "../../outreach/components/OutreachPanel.vue";
import { STAGE_LABEL, type Stage } from "@/api/opportunities";
import { fetchProducts, type Product } from "@/api/products";
import BoardCard from "../components/BoardCard.vue";
import DueTodayPanel from "../components/DueTodayPanel.vue";
import LostForm from "../components/LostForm.vue";
import LostStrip from "../components/LostStrip.vue";
import { COLUMNS, NEXT_STAGE, usePipeline } from "../composables/usePipeline";

const INTENT_CLASS: Record<string, string> = { cold: "muted", warm: "potential", hot: "precise" };
const INTENT_LABEL: Record<string, string> = { cold: "冷", warm: "温", hot: "热" };

const products = ref<Product[]>([]);
const {
  productId, error, busyId, lostTarget, dueToday, lostList,
  reload, advance, confirmLost, reopen, byStage,
} = usePipeline();

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
    <DueTodayPanel
      v-if="dueToday.length"
      :items="dueToday"
    />

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
          @lost="lostTarget = opp"
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
    <LostForm
      v-if="lostTarget"
      :key="lostTarget.opportunity_id"
      :target="lostTarget"
      :busy="busyId != null"
      @confirm="confirmLost"
      @cancel="lostTarget = null"
    />

    <!-- 功能区 4：已流失（紧凑条） -->
    <LostStrip
      v-if="lostList.length"
      :items="lostList"
      :busy-id="busyId"
      @reopen="reopen"
    />

    <!-- 功能区 5：邮件模板与发送日志 -->
    <OutreachPanel />
  </div>
</template>

<style scoped>
.pipeline-page { display: flex; flex-direction: column; gap: 12px; }
.pipeline-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 18px; }
.pipeline-header h1 { margin: 0; }
.pipeline-filter { min-width: 200px; }


.board { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; align-items: start; }
.board-col { background: #f0f4f5; border: 1px solid var(--line); border-radius: 8px; padding: 8px; min-height: 120px; }
.board-col h3 { margin: 0 0 8px; font-size: 12px; display: flex; align-items: center; gap: 6px; color: var(--ink-soft); }
.board-col .count { background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 0 7px; font-size: 11px; }
.board-empty { text-align: center; padding: 20px 0; }


@media (max-width: 1100px) { .board { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 720px) { .board { grid-template-columns: repeat(2, 1fr); } .pipeline-header { flex-direction: column; align-items: stretch; } }
</style>
