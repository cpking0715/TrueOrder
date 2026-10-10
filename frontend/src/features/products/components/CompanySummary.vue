<script setup lang="ts">
import type { CompanyDetail } from "@/api/products";

defineProps<{
  company: CompanyDetail["company"];
  tier?: string | null;
}>();

const tierLabel: Record<string, string> = {
  precise: "精准客户",
  potential: "潜在客户",
  excluded: "已排除",
};
</script>

<template>
  <header class="company-summary">
    <h2>
      {{ company.name }}
      <span
        v-if="tier"
        :class="['badge', tier]"
      >{{ tierLabel[tier] }}</span>
    </h2>
    <p class="muted small">
      {{ company.country }}<span v-if="company.city"> · {{ company.city }}</span>
      · 规范名：{{ company.normalized_name }}
    </p>
    <p
      v-if="company.same_name_conflict"
      class="alert small"
    >
      <span class="badge conflict">同名冲突</span>
      不同城市线索出现同一名称，未自动合并——请人工核对再联系。
    </p>
    <p
      v-if="company.address"
      class="muted small"
    >
      {{ company.address }}
    </p>
  </header>
</template>
