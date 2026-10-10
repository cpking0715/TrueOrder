<script setup lang="ts">
import type { Tier } from "@/api/products";

defineProps<{ tier: Tier; counts: Record<string, number> }>();
const emit = defineEmits<{ change: [tier: Tier] }>();

const tabs: Array<{ key: Tier; label: string }> = [
  { key: "potential", label: "潜在客户" },
  { key: "precise", label: "精准客户" },
  { key: "excluded", label: "已排除" },
];
</script>

<template>
  <div
    class="tabs"
    role="tablist"
  >
    <button
      v-for="tab in tabs"
      :key="tab.key"
      role="tab"
      :aria-selected="tab.key === tier"
      :class="['t-' + tab.key, { active: tab.key === tier }]"
      :data-testid="`tab-${tab.key}`"
      @click="emit('change', tab.key)"
    >
      {{ tab.label }}<span class="num">（{{ counts?.[tab.key] ?? 0 }}）</span>
    </button>
  </div>
</template>
