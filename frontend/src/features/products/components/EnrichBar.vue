<script setup lang="ts">
import { computed, ref } from "vue";
import { enrichBuyers, fetchEnrichUsage, type EnrichEstimate } from "@/api/contacts";
import type { BuyerQuery } from "@/api/products";
import DiscoverButton from "./DiscoverButton.vue";

const props = defineProps<{ productId: number; query: BuyerQuery }>();

const limit = ref(10);
const busy = ref(false);
const error = ref("");
const estimate = ref<EnrichEstimate | null>(null);
const executedCount = ref(0);
const usage = ref<string>("");

function buildRequest(confirm: boolean) {
  return {
    tier: props.query.tier,
    audience: props.query.audience,
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
    e.capped_by_quota > 0
      ? `将入队 ${e.credits_needed} 家（其中约 ${e.capped_by_quota} 家因额度可能延期到明日，免费源命中则不消耗额度）`
      : `可补全 ${e.candidates} 家`,
    e.skipped_has_contacts ? `已有联系人跳过 ${e.skipped_has_contacts}` : "",
    e.skipped_queried_recently ? `近期查过跳过 ${e.skipped_queried_recently}` : "",
  ];
  return parts.filter(Boolean).join("，");
});

async function askEstimate() {
  error.value = "";
  executedCount.value = 0;
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
    executedCount.value = result.enqueued ?? 0;
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
      <span class="eyebrow">第 1 步 · 选择范围</span>
      <label class="small">
        补全当前筛选前
        <input
          v-model.number="limit"
          class="input-narrow"
          type="number"
          min="1"
          max="50"
          data-testid="enrich-limit"
        >
        家的联系方式
      </label>
      <button
        class="small"
        :disabled="busy"
        data-testid="enrich-estimate"
        @click="askEstimate"
      >
        {{ busy ? "预估中…" : "预估额度" }}
      </button>
      <DiscoverButton :product-id="productId" />

      <span
        v-if="executedCount > 0"
        class="small muted"
        data-testid="enrich-executed"
      >已入队 {{ executedCount }} 家——在<a href="#/jobs">任务页</a>跟踪进度，worker 执行后打开公司抽屉查看联系人。</span>
    </template>
    <template v-else>
      <span class="eyebrow">第 2 步 · 确认消耗额度</span>
      <span class="small muted">前 {{ limit }} 家 · <a
        href="#"
        class="marine-link"
        @click.prevent="estimate = null"
      >重新预估</a></span>
      <span
        class="small"
        role="status"
        aria-live="polite"
        data-testid="enrich-estimate-text"
      >{{ estimateText }}</span>
      <button
        class="small primary"
        :disabled="busy || estimate.credits_needed === 0"
        data-testid="enrich-confirm"
        @click="confirmRun"
      >
        {{ busy ? "执行中…" : "确认执行" }}
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
