<script setup lang="ts">
import type { CompanyDetail } from "@/api/products";

defineProps<{ reasons: CompanyDetail["scores"][number]["reasons"] }>();
const emit = defineEmits<{ locate: [billId: number] }>();
</script>

<template>
  <ul
    class="reason-list"
    data-testid="reason-list"
  >
    <li
      v-for="(reason, index) in reasons"
      :key="index"
    >
      <span>{{ reason.text }}</span>
      <button
        v-for="id in reason.bill_ids"
        :key="id"
        class="bill-chip-link"
        data-testid="bill-chip"
        title="点击定位对应提单"
        @click="emit('locate', id)"
      >
        提单 #{{ id }}
      </button>
    </li>
  </ul>
</template>

<style scoped>
.bill-chip-link {
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  background: #eef1f5;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 1px 7px;
  color: var(--ink-soft);
}
.bill-chip-link:hover {
  border-color: var(--accent);
  color: var(--accent);
}
</style>
