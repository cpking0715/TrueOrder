<script setup lang="ts">
import type { CompanyDetail } from "@/api/products";

defineProps<{ score: CompanyDetail["scores"][number] }>();
</script>

<template>
  <div class="summary-grid">
    <div class="box">
      <div class="num">
        {{ score.shipments }}
      </div>票数
    </div>
    <div class="box">
      <div class="num code">
        {{ score.last_arrival ?? "—" }}
      </div>最近到港
    </div>
    <div class="box">
      <div class="num small">
        {{ score.suppliers.length }}
      </div>供货方
    </div>
  </div>
</template>
