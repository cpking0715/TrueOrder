<script setup lang="ts">
defineProps<{ autoHs: { hs_code: string; bill_count: number } | null; busy: boolean; show: boolean }>();
const emit = defineEmits<{ accept: [] }>();
</script>

<template>
  <span
    v-if="busy && show"
    class="muted small"
  >推荐中…</span>
  <button
    v-else-if="autoHs && show"
    class="badge precise small"
    data-testid="hs-auto-chip"
    title="AI 从品名推断，点击填入"
    @click="emit('accept')"
  >
    建议 {{ autoHs.hs_code }}{{ autoHs.bill_count > 0 ? `（库内 ${autoHs.bill_count} 票验证）` : "（AI 推荐）" }}
  </button>
</template>
