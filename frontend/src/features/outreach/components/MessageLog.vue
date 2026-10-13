<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchMessages, type Message } from "@/api/outreach";

const messages = ref<Message[]>([]);
const error = ref("");

const STATUS_LABEL: Record<string, string> = {
  queued: "排队中", sending: "发送中", sent: "已发送",
  failed: "失败", bounced: "退信", suppressed: "已抑制",
};
const STATUS_CLASS: Record<string, string> = {
  sent: "precise", failed: "excluded", queued: "potential",
  suppressed: "warn", sending: "info", bounced: "excluded",
};

async function reload() {
  try {
    messages.value = await fetchMessages();
    error.value = "";
  } catch (e) {
    error.value = (e as Error).message;
  }
}

onMounted(reload);
</script>

<template>
  <section data-testid="message-log">
    <h3>发送日志（{{ messages.length }}）</h3>
    <p
      v-if="error"
      class="error small"
    >
      {{ error }}
    </p>
    <p
      v-if="!messages.length && !error"
      class="muted small"
    >
      暂无发送记录
    </p>
    <ul
      v-else
      class="contact-list"
    >
      <li
        v-for="m in messages"
        :key="m.id"
      >
        <span
          class="badge"
          :class="STATUS_CLASS[m.status] ?? 'muted'"
        >{{ STATUS_LABEL[m.status] ?? m.status }}</span>
        <span>{{ m.subject }}</span>
        <span
          v-if="m.error"
          class="error small"
        >{{ m.error }}</span>
      </li>
    </ul>
  </section>
</template>
