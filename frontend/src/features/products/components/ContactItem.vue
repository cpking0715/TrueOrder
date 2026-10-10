<script setup lang="ts">
import { ref } from "vue";
import type { Contact, ContactUpdate } from "@/api/contacts";
import ContactForm from "./ContactForm.vue";

defineProps<{ contact: Contact }>();
const emit = defineEmits<{
  update: [payload: ContactUpdate];
  toggleDnc: [];
  delete: [];
}>();

const editing = ref(false);

const verifyLabel: Record<string, string> = {
  unknown: "未验证",
  valid: "有效",
  invalid: "无效",
  bounced: "退信",
};
</script>

<template>
  <li :data-testid="`contact-row-${contact.contact_id}`">
    <ContactForm
      v-if="editing"
      :contact="contact"
      submit-label="保存"
      @submit="emit('update', $event); editing = false"
      @cancel="editing = false"
    />
    <template v-else>
      <strong>{{ contact.name ?? "（通用邮箱）" }}</strong>
      <span v-if="contact.title"> · {{ contact.title }}</span>
      <div class="muted small">
        <span
          v-if="contact.email"
          class="code"
        >{{ contact.email }}</span>
        <span
          v-if="contact.phone"
          class="code"
        > · {{ contact.phone }}</span>
      </div>
      <div class="tags">
        <span
          v-if="contact.is_generic"
          class="badge"
        >通用邮箱</span>
        <span
          v-if="contact.do_not_contact"
          class="badge warn"
          data-testid="dnc-badge"
        >不再联系</span>
        <span class="badge muted">{{ verifyLabel[contact.verify_status] ?? contact.verify_status }}</span>
        <span class="badge muted">来源：{{ contact.source }}</span>
      </div>
      <div class="actions">
        <button
          class="small ghost"
          @click="editing = true"
        >
          编辑
        </button>
        <button
          class="small ghost"
          :data-testid="`toggle-dnc-${contact.contact_id}`"
          @click="emit('toggleDnc')"
        >
          {{ contact.do_not_contact ? "恢复联系" : "标记不再联系" }}
        </button>
        <button
          class="small ghost"
          :data-testid="`delete-contact-${contact.contact_id}`"
          @click="emit('delete')"
        >
          删除
        </button>
      </div>
    </template>
  </li>
</template>
