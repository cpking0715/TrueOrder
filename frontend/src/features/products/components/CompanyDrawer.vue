<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import AcquireSection from "./AcquireSection.vue";
import BillsSection from "./BillsSection.vue";
import CompanySummary from "./CompanySummary.vue";
import DrawerHead from "./DrawerHead.vue";
import ScoreSection from "./ScoreSection.vue";
import { useCompanyDrawer } from "../composables/useCompanyDrawer";

const props = defineProps<{
  companyId: number | null;
  productId: number;
  audience?: string;
}>();
const emit = defineEmits<{ close: [] }>();

const { detail, loading, error, score, reload } = useCompanyDrawer(
  () => props.companyId,
  () => props.productId,
  () => props.audience,
);

const highlightId = ref<number | null>(null);
const billsExpanded = ref(false); // 长表默认只渲染前 50 票
const BILL_PAGE = 50;
let lastFocus: HTMLElement | null = null; // 打开前的焦点元素，关闭后归还

// Esc 关抽屉：窗口级监听，随抽屉开关挂/卸
function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown);
  document.body.style.overflow = "";
});

watch(
  () => props.companyId,
  (id) => {
    window.removeEventListener("keydown", onKeydown);
    if (id == null) {
      billsExpanded.value = false;
      document.body.style.overflow = ""; // 解锁背后滚动
      lastFocus?.focus();
      lastFocus = null;
      return;
    }
    window.addEventListener("keydown", onKeydown);
    lastFocus = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden"; // 锁背后滚动
    void nextTick(() => {
      document.querySelector<HTMLElement>("[data-testid='drawer-close']")?.focus();
    });
  },
  { immediate: true },
);

// F1：点击理由里的提单号 → 展开长表 → 滚动定位并高亮；高亮期间提供返回链路
async function locateBill(billId: number) {
  highlightId.value = billId;
  billsExpanded.value = true; // 目标行可能在折叠区外
  await new Promise((resolve) => setTimeout(resolve, 0));
  document.getElementById(`bill-row-${billId}`)?.scrollIntoView({
    behavior: "smooth",
    block: "center",
  });
  setTimeout(() => {
    if (highlightId.value === billId) highlightId.value = null;
  }, 2500);
}

function backToReasons() {
  document.getElementById("drawer-score")?.scrollIntoView({ behavior: "smooth" });
  highlightId.value = null;
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
      aria-modal="true"
      aria-label="公司详情"
      data-testid="company-drawer"
    >
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
        <span class="error">加载失败：{{ error }}</span>
      </div>
      <template v-else-if="detail">
        <DrawerHead
          :title="detail.company.name"
          @close="emit('close')"
        />
        <CompanySummary
          :company="detail.company"
          :tier="score?.tier ?? null"
        />

        <section id="drawer-score">
          <ScoreSection
            v-if="score"
            :score="score"
            @locate="locateBill"
          />
        </section>

        <a
          v-if="highlightId != null"
          class="locate-back"
          role="link"
          @click="backToReasons"
        >↑ 返回得分理由</a>

        <BillsSection
          :bills="detail.bills"
          :shown="billsExpanded ? detail.bills : detail.bills.slice(0, BILL_PAGE)"
          :expanded="billsExpanded"
          :highlight-id="highlightId"
          @expand="billsExpanded = true"
        />

        <AcquireSection
          :company="detail.company"
          @confirmed="reload"
        />
      </template>
    </aside>
  </Teleport>
</template>
