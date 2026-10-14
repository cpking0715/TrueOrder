<script setup lang="ts">
import { computed } from "vue";
import { withApiToken } from "@/api/client";
import EnrichBar from "./EnrichBar.vue";
import type { FilterState } from "../composables/useBuyerFilters";

const props = defineProps<{ productId: number; filters: FilterState; exportUrl: string }>();

// 联系人导出与买家导出共用同一筛选参数：取 buyers 导出 URL 的查询串换成 contacts 路径
const contactsExportUrl = computed(() => {
  const url = props.exportUrl;
  const search = url.includes("?") ? url.slice(url.indexOf("?")) : "";
  return withApiToken(`/api/products/${props.productId}/contacts/export.csv${search}`);
});
</script>

<template>
  <div class="detail-actions">
    <EnrichBar
      :product-id="productId"
      :query="{
        tier: filters.tier,
        q: filters.q,
        country: filters.country,
        minShipments: filters.minShipments,
      }"
    />
    <span class="actions">
      <a
        class="btn primary"
        :href="exportUrl"
        download
        data-testid="export-button"
        title="导出当前筛选的全部结果（不受列表显示条数限制）"
      >
        导出买家 CSV
      </a>
      <a
        class="btn"
        :href="contactsExportUrl"
        download
        data-testid="export-contacts-button"
        title="按当前筛选导出联系人（默认排除不再联系与无效邮箱）"
      >
        导出联系人 CSV
      </a>
    </span>
  </div>
</template>
