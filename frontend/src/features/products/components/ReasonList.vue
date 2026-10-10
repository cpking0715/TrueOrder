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
