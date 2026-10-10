<script setup lang="ts">
import { reactive } from "vue";
import type { Contact } from "@/api/contacts";

const props = defineProps<{
  contact?: Contact | null;
  submitLabel: string;
}>();
const emit = defineEmits<{
  submit: [payload: { name: string | null; title: string; email: string | null; phone: string | null }];
  cancel: [];
}>();

const form = reactive({
  name: props.contact?.name ?? "",
  title: props.contact?.title ?? "",
  email: props.contact?.email ?? "",
  phone: props.contact?.phone ?? "",
});

function submit() {
  emit("submit", {
    name: form.name.trim() || null,
    title: form.title.trim(),
    email: form.email.trim() || null,
    phone: form.phone.trim() || null,
  });
}
</script>

<template>
  <form
    class="contact-form"
    data-testid="contact-form"
    @submit.prevent="submit"
  >
    <input
      v-model="form.name"
      placeholder="姓名"
      aria-label="联系人姓名"
      data-testid="contact-name"
    >
    <input
      v-model="form.title"
      placeholder="职位"
      aria-label="联系人职位"
    >
    <input
      v-model="form.email"
      placeholder="邮箱"
      aria-label="联系人邮箱"
      data-testid="contact-email"
    >
    <input
      v-model="form.phone"
      placeholder="电话"
      aria-label="联系人电话"
    >
    <button type="submit">
      {{ submitLabel }}
    </button>
    <button
      type="button"
      class="ghost"
      @click="emit('cancel')"
    >
      取消
    </button>
  </form>
</template>
