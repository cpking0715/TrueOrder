<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  createKitInquiry, fetchKitInquiries, piPdfUrl, setInquiryStatus,
  type InquiryStatus, type KitInquiry, type KitInquiryIn,
} from "@/api/kit";
import { useAsync } from "@/composables/useAsync";
import InquiryForm from "../components/InquiryForm.vue";
import KitNav from "../components/KitNav.vue";
import { useKitPickers } from "../composables/useKitPickers";

// 与后端领域状态流一致；非法转换由后端 422 拦截并在页面提示
const NEXT: Record<string, InquiryStatus[]> = {
  new: ["quoted", "sample", "lost"],
  quoted: ["sample", "won", "lost"],
  sample: ["quoted", "won", "lost"],
  won: [],
  lost: ["new"],
};
const LABEL: Record<string, string> = { new: "新询盘", quoted: "已报价", sample: "等样品", won: "赢单", lost: "丢单" };

const { buyers, products, loadPickers } = useKitPickers();
const inquiries = ref<KitInquiry[]>([]);
const { busy, error, run } = useAsync();

async function load() {
  await run(async () => {
    await loadPickers();
    inquiries.value = await fetchKitInquiries();
  });
}

async function add(payload: KitInquiryIn) {
  const row = await run(() => createKitInquiry(payload));
  if (row) inquiries.value = [row, ...inquiries.value];
}

async function move(row: KitInquiry, status: InquiryStatus) {
  const updated = await run(() => setInquiryStatus(row.id, status));
  if (updated) inquiries.value = inquiries.value.map((r) => (r.id === row.id ? updated : r));
}

onMounted(load);
</script>

<template>
  <div class="panel">
    <KitNav />
    <h1>询盘与报价</h1>
    <InquiryForm
      :buyers="buyers"
      :products="products"
      :busy="busy"
      @submit="add"
    />
    <p
      v-if="error"
      class="error small"
    >
      {{ error }}
    </p>
    <table class="kit-table">
      <thead><tr><th>买家</th><th>产品</th><th>数量×单价</th><th>金额</th><th>状态</th><th /></tr></thead>
      <tbody>
        <tr
          v-for="r in inquiries"
          :key="r.id"
          :data-testid="`kit-inquiry-${r.id}`"
        >
          <td>{{ r.company_name }}</td>
          <td>{{ r.product_name }}</td>
          <td>{{ r.quantity }} × {{ r.unit_price }}</td>
          <td>{{ r.currency }} {{ r.total }}</td>
          <td>
            <span class="badge info">{{ r.status_label }}</span>
            <button
              v-for="s in NEXT[r.status]"
              :key="s"
              type="button"
              class="small"
              @click="move(r, s)"
            >
              → {{ LABEL[s] }}
            </button>
          </td>
          <td>
            <a
              :href="piPdfUrl(r.id)"
              download
            >导出 PI</a>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.kit-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.kit-table th, .kit-table td { text-align: left; padding: 6px; border-bottom: 1px solid var(--line); }
</style>
