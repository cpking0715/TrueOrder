<script setup lang="ts">
import type { Opportunity } from "@/api/opportunities";

defineProps<{ items: Opportunity[]; busyId: number | null }>();
const emit = defineEmits<{ reopen: [opp: Opportunity] }>();
</script>

<template>
  <div class="panel lost-strip">
    <h3>已流失</h3>
    <span
      v-for="o in items"
      :key="o.opportunity_id"
      class="lost-chip"
      :title="o.closed_reason ?? ''"
      :data-testid="`lost-${o.opportunity_id}`"
    >
      {{ o.company_name }}：{{ (o.closed_reason ?? "").slice(0, 20) }}
      <button
        class="small ghost"
        :disabled="busyId === o.opportunity_id"
        @click="emit('reopen', o)"
      >
        重开
      </button>
    </span>
  </div>
</template>

<style scoped>
.lost-strip { padding: 10px 18px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.lost-strip h3 { margin: 0; font-size: 12px; color: var(--ink-soft); }
.lost-chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border: 1px dashed var(--line); border-radius: 6px; font-size: 12px; color: var(--ink-soft); }
</style>
