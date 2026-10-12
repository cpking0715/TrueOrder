<script setup lang="ts">
import type { Opportunity } from "@/api/opportunities";

defineProps<{
  opp: Opportunity;
  busy: boolean;
  showAdvance: boolean;
  showLost: boolean;
  intentBadge: string;
  intentLabel: string;
}>();
const emit = defineEmits<{ advance: []; lost: [] }>();
</script>

<template>
  <div
    class="card"
    :data-testid="`card-${opp.opportunity_id}`"
  >
    <div class="card-top">
      <strong>{{ opp.company_name }}</strong>
      <span
        class="badge"
        :class="intentBadge"
      >{{ intentLabel }}</span>
    </div>
    <p
      v-if="opp.owner_note"
      class="note"
    >
      {{ opp.owner_note }}
    </p>
    <div class="card-meta">
      <span class="code small muted">{{ opp.next_follow_up_on ?? "未排期" }}</span>
    </div>
    <div class="card-actions">
      <button
        v-if="showAdvance"
        class="small ghost"
        :disabled="busy"
        title="推进到下一阶段"
        @click="emit('advance')"
      >
        →
      </button>
      <button
        v-if="showLost"
        class="small ghost danger"
        :disabled="busy"
        title="标记流失（需填原因）"
        @click="emit('lost')"
      >
        ×
      </button>
    </div>
  </div>
</template>

<style scoped>
.card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.card-top { display: flex; align-items: center; justify-content: space-between; gap: 4px; }
.card-top strong { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.note { margin: 0; font-size: 11px; color: var(--ink-soft); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-meta { display: flex; justify-content: flex-end; }
.card-actions { display: flex; gap: 4px; justify-content: flex-end; padding-top: 2px; border-top: 1px dashed var(--line); }
.card-actions button { padding: 0 8px; min-width: 28px; font-size: 14px; line-height: 20px; }
.card-actions .danger:hover { border-color: var(--stamp); color: var(--stamp); }
</style>
