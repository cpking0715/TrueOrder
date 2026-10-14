<script setup lang="ts">
import { STAGE_LABEL, type Opportunity, type Stage } from "@/api/opportunities";

defineProps<{ items: Opportunity[] }>();
</script>

<template>
  <div
    class="panel due-panel"
    data-testid="due-today"
  >
    <span class="badge excluded">今日待跟进 {{ items.length }}</span>
    <div
      v-for="o in items"
      :key="o.opportunity_id"
      class="due-chip"
    >
      <strong>{{ o.company_name }}</strong>
      <span class="muted small">{{ STAGE_LABEL[o.stage as Stage] }} · {{ o.next_follow_up_on }}</span>
    </div>
  </div>
</template>

<style scoped>
.due-panel { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 18px; }
.due-chip { display: flex; flex-direction: column; padding: 4px 10px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
</style>
