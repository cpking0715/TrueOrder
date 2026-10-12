<script setup lang="ts">
import type { CompanyDetail } from "@/api/products";
import BillTable from "./BillTable.vue";

defineProps<{
  bills: CompanyDetail["bills"];
  shown: CompanyDetail["bills"];  // 折叠态实际渲染的切片
  expanded: boolean;
  highlightId: number | null;
}>();
const emit = defineEmits<{ expand: [] }>();
</script>

<template>
  <section id="drawer-bills">
    <h2>
      提单（最近 {{ bills.length }} 票<template v-if="!expanded && shown.length < bills.length">
        ，显示前 {{ shown.length }} 票
      </template>）
    </h2>
    <div class="table-scroll">
      <BillTable
        :bills="shown"
        :highlight-id="highlightId"
      />
      <button
        v-if="!expanded && bills.length > shown.length"
        class="small ghost"
        data-testid="expand-bills"
        style="margin-top: 8px"
        @click="emit('expand')"
      >
        显示全部 {{ bills.length }} 票
      </button>
    </div>
  </section>
</template>
