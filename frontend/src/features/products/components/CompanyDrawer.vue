<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { fetchCompany, type CompanyDetail } from "@/api/products";
import BillTable from "./BillTable.vue";
import ReasonList from "./ReasonList.vue";

const props = defineProps<{ companyId: number | null; productId: number }>();
const emit = defineEmits<{ close: [] }>();

const detail = ref<CompanyDetail | null>(null);
const loading = ref(false);
const error = ref("");

const score = computed(() => {
  if (!detail.value) return null;
  return (
    detail.value.scores.find((s) => s.product_id === props.productId) ??
    detail.value.scores[0] ??
    null
  );
});

watch(
  () => props.companyId,
  async (id) => {
    if (id == null) {
      detail.value = null;
      return;
    }
    loading.value = true;
    error.value = "";
    try {
      detail.value = await fetchCompany(id, props.productId);
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);
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
        <h2>{{ detail.company.name }}</h2>
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
          <div class="summary-grid">
            <div class="box">
              <div class="num">
                {{ score.shipments }}
              </div>票数
            </div>
            <div class="box">
              <div class="num">
                {{ score.last_arrival ?? "—" }}
              </div>最近到港
            </div>
            <div class="box">
              <div class="num small">
                {{ score.suppliers.length }}
              </div>供货方
            </div>
          </div>
          <h2>得分理由</h2>
          <ReasonList :reasons="score.reasons" />
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
        <BillTable :bills="detail.bills" />
      </template>
    </aside>
  </Teleport>
</template>
