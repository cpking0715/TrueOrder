<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { fetchCompany, type CompanyDetail } from "@/api/products";
import BillTable from "./BillTable.vue";
import ReasonList from "./ReasonList.vue";
import ScoreSummary from "./ScoreSummary.vue";

const props = defineProps<{
  companyId: number | null;
  productId: number;
  audience?: string;
}>();
const emit = defineEmits<{ close: [] }>();

const detail = ref<CompanyDetail | null>(null);
const loading = ref(false);
const error = ref("");
const highlightId = ref<number | null>(null);

const score = computed(() => {
  if (!detail.value) return null;
  // both 产品按当前受众取得分，避免两类受众串台（F5）
  const byProduct = detail.value.scores.filter((s) => s.product_id === props.productId);
  return byProduct.find((s) => !props.audience || s.audience === props.audience)
    ?? byProduct[0]
    ?? detail.value.scores[0]
    ?? null;
});

const tierLabel: Record<string, string> = {
  precise: "精准客户",
  potential: "潜在客户",
  excluded: "已排除",
};

// Esc 关抽屉：窗口级监听，随抽屉开关挂/卸
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

watch(
  () => [props.companyId, props.productId, props.audience] as const,
  async ([id]) => {
    window.removeEventListener("keydown", onKeydown);
    if (id == null) {
      detail.value = null;
      return;
    }
    window.addEventListener("keydown", onKeydown);
    loading.value = true;
    error.value = "";
    try {
      detail.value = await fetchCompany(id, props.productId, props.audience);
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

// F1：点击理由里的提单号 → 滚动定位并高亮对应提单行
async function locateBill(billId: number) {
  highlightId.value = billId;
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.getElementById(`bill-row-${billId}`)?.scrollIntoView({
    behavior: "smooth",
    block: "center",
  });
  setTimeout(() => {
    if (highlightId.value === billId) highlightId.value = null;
  }, 2500);
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="companyId != null"
      class="drawer-mask"
      @click="emit('close')"
    />
    <aside
      v-if="companyId != null"
      class="drawer"
      role="dialog"
      aria-label="公司详情"
      data-testid="company-drawer"
    >
      <button
        class="close"
        data-testid="drawer-close"
        @click="emit('close')"
      >
        关闭
      </button>
      <div
        v-if="loading"
        class="empty"
      >
        加载中…
      </div>
      <div
        v-else-if="error"
        class="empty"
      >
        加载失败：{{ error }}
      </div>
      <template v-else-if="detail">
        <h2>
          {{ detail.company.name }}
          <span
            v-if="score"
            :class="['badge', score.tier]"
          >{{ tierLabel[score.tier] }}</span>
        </h2>
        <p class="muted small">
          {{ detail.company.country }}<span v-if="detail.company.city"> · {{ detail.company.city }}</span>
          · 规范名：{{ detail.company.normalized_name }}
        </p>
        <p
          v-if="detail.company.same_name_conflict"
          class="badge conflict"
        >
          同名冲突：不同城市线索出现同一名称，未自动合并
        </p>
        <p
          v-if="detail.company.address"
          class="muted small"
        >
          {{ detail.company.address }}
        </p>

        <template v-if="score">
          <ScoreSummary :score="score" />
          <h2>得分理由</h2>
          <ReasonList
            :reasons="score.reasons"
            @locate="locateBill"
          />
          <p
            v-if="score.suppliers.length"
            class="small muted"
          >
            供货方：{{ score.suppliers.join("；") }}
          </p>
        </template>

        <h2 style="margin-top: 16px">
          提单（最近 500 票内）
        </h2>
        <BillTable
          :bills="detail.bills"
          :highlight-id="highlightId"
        />
      </template>
    </aside>
  </Teleport>
</template>
