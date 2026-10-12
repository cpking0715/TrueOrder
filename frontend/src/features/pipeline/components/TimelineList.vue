<script setup lang="ts">
import type { Activity } from "@/api/opportunities";

defineProps<{ timeline: Activity[] }>();

const KIND_LABEL: Record<string, string> = {
  email_out: "发信", email_in: "回信", call: "电话",
  whatsapp: "WhatsApp", note: "备注", stage_change: "阶段",
};
</script>

<template>
  <ul class="contact-list">
    <li
      v-for="a in timeline"
      :key="a.activity_id"
      class="small"
    >
      <span class="badge">{{ KIND_LABEL[a.kind] ?? a.kind }}</span>
      {{ a.summary }}
      <span v-if="a.intent_after">→ {{ a.intent_after }}</span>
    </li>
  </ul>
  <p
    v-if="!timeline.length"
    class="muted small"
  >
    暂无跟进记录
  </p>
</template>
