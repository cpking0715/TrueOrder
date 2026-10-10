<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { fetchCompany, type CompanyDetail } from "@/api/products";
import BillTable from "./BillTable.vue";
import CompanySummary from "./CompanySummary.vue";
import ContactsPanel from "./ContactsPanel.vue";
import WebsiteField from "./WebsiteField.vue";
import ScoreSection from "./ScoreSection.vue";

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

// Esc 关抽屉：窗口级监听，随抽屉开关挂/卸
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

// 关闭后/切换公司在途的旧响应不允许写入（与买家列表的 requestSeq 同口径）
let requestSeq = 0;

async function load(id: number) {
  const seq = ++requestSeq;
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchCompany(id, props.productId, props.audience);
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
  if (props.companyId != null) void load(props.companyId);
}

watch(
  () => [props.companyId, props.productId, props.audience] as const,
  ([id]) => {
    window.removeEventListener("keydown", onKeydown);
    if (id == null) {
      detail.value = null;
      return;
    }
    window.addEventListener("keydown", onKeydown);
    void nextTick(() => {
      document.querySelector<HTMLElement>("[data-testid='drawer-close']")?.focus();
    });
    void load(id);
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
        <CompanySummary
          :company="detail.company"
          :tier="score?.tier ?? null"
        />

        <ScoreSection
          v-if="score"
          :score="score"
          @locate="locateBill"
        />

        <h2>
          提单（最近 500 票内）
        </h2>
        <div class="table-scroll">
          <BillTable
            :bills="detail.bills"
            :highlight-id="highlightId"
          />
        </div>

        <WebsiteField
          :company-id="detail.company.company_id"
          :website="detail.company.website"
          :confirmed="detail.company.website_confirmed"
          :confidence="detail.company.website_confidence"
          @confirmed="reload"
        />
        <ContactsPanel :company-id="detail.company.company_id" />
      </template>
    </aside>
  </Teleport>
</template>
