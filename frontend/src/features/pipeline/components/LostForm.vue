<script setup lang="ts">
import { ref } from "vue";
import type { Opportunity } from "@/api/opportunities";

defineProps<{ target: Opportunity; busy: boolean }>();
const emit = defineEmits<{ confirm: [reason: string]; cancel: [] }>();
const reason = ref("");

function submit() {
  if (reason.value.trim()) emit("confirm", reason.value);
}
</script>

<template>
  <div
    class="panel lost-form"
    data-testid="lost-form"
  >
    <span>流失 <strong>{{ target.company_name }}</strong>，原因：</span>
    <input
      v-model="reason"
      placeholder="必填"
      data-testid="lost-reason"
      @keydown.enter.prevent="submit"
    >
    <button
      class="small primary"
      :disabled="!reason.trim() || busy"
      @click="submit"
    >
      确认流失
    </button>
    <button
      class="small ghost"
      @click="emit('cancel')"
    >
      取消
    </button>
  </div>
</template>

<style scoped>
.lost-form { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; border-left: 3px solid var(--stamp); padding: 10px 18px; }
</style>
