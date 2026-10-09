<script setup lang="ts">
import type { CompanyDetail } from "@/api/products";

defineProps<{ reasons: CompanyDetail["scores"][number]["reasons"] }>();
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
      <span
        v-for="id in reason.bill_ids"
        :key="id"
        class="bill-chip"
        data-testid="bill-chip"
      >
        提单 #{{ id }}
      </span>
    </li>
  </ul>
</template>
