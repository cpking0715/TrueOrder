<script setup lang="ts">
import { computed, ref } from "vue";
import { enrichBuyers, fetchEnrichUsage, type EnrichEstimate } from "@/api/contacts";
import type { BuyerQuery } from "@/api/products";

const props = defineProps<{ productId: number; query: BuyerQuery }>();

const limit = ref(10);
const busy = ref(false);
const error = ref("");
const estimate = ref<EnrichEstimate | null>(null);
const executed = ref("");
const usage = ref<string>("");

function buildRequest(confirm: boolean) {
  return {
    tier: props.query.tier,
    q: props.query.q,
    country: props.query.country,
    min_shipments: props.query.minShipments,
    limit: limit.value,
    confirm,
  };
}

async function loadUsageHint() {
  try {
    const u = await fetchEnrichUsage();
    const provider = u.configured ? "Hunter" : "未配置 Hunter Key（演示数据源）";
    usage.value = `补全服务：${provider}；今日剩余额度 ${u.remaining}/${u.daily_cap}`;
  } catch {
    usage.value = "";
  }
}

const estimateText = computed(() => {
  const e = estimate.value;
  if (!e) return "";
  const parts = [
    `可补全 ${e.candidates} 家`,
    e.skipped_has_contacts ? `已有联系人跳过 ${e.skipped_has_contacts}` : "",
    e.skipped_queried_recently ? `近期查过跳过 ${e.skipped_queried_recently}` : "",
    e.capped_by_quota ? `额度不足截断 ${e.capped_by_quota}` : "",
  ];
  return parts.filter(Boolean).join("，");
});

async function askEstimate() {
  error.value = "";
  executed.value = "";
  busy.value = true;
  try {
    estimate.value = await enrichBuyers(props.productId, buildRequest(false));
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}

async function confirmRun() {
  error.value = "";
  busy.value = true;
  try {
    const result = await enrichBuyers(props.productId, buildRequest(true));
    executed.value = `已入队 ${result.enqueued} 家（任务页可跟踪进度），worker 执行后打开公司抽屉查看联系人。`;
    estimate.value = null;
    void loadUsageHint();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}

void loadUsageHint();
</script>

<template>
  <div
    class="enrichbar"
    data-testid="enrich-bar"
  >
    <template v-if="!estimate">
      <label class="small">
        补全当前筛选前
        <input
          v-model.number="limit"
          type="number"
          min="1"
          max="50"
          data-testid="enrich-limit"
          style="width: 64px"
        >
        家的联系方式
      </label>
      <button
        class="small"
        :disabled="busy"
        data-testid="enrich-estimate"
        @click="askEstimate"
      >
        估计额度
      </button>
      <span
        v-if="executed"
        class="small muted"
        data-testid="enrich-executed"
      >{{ executed }}</span>
    </template>
    <template v-else>
      <span
        class="small"
        data-testid="enrich-estimate-text"
      >{{ estimateText }}</span>
      <button
        class="small primary"
        :disabled="busy || estimate.candidates === 0"
        data-testid="enrich-confirm"
        @click="confirmRun"
      >
        确认执行
      </button>
      <button
        class="small ghost"
        data-testid="enrich-cancel"
        @click="estimate = null"
      >
        取消
      </button>
    </template>
    <span
      v-if="usage"
      class="small muted"
    >{{ usage }}</span>
    <p
      v-if="error"
      class="badge excluded"
      role="alert"
    >
      {{ error }}
    </p>
  </div>
</template>
