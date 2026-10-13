<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  createTemplate,
  deleteTemplate,
  fetchTemplates,
  type Template,
} from "@/api/outreach";

const templates = ref<Template[]>([]);
const error = ref("");
const adding = ref(false);
const name = ref("");
const subject = ref("");
const body = ref("");

const VAR_HINT = "变量：{company} {contact_name} {product} {last_arrival} {shipments} {supplier} {sender_name}";

async function reload() {
  try {
    templates.value = await fetchTemplates();
    error.value = "";
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function submit() {
  error.value = "";
  try {
    await createTemplate({ name: name.value, subject: subject.value, body: body.value });
    adding.value = false;
    name.value = ""; subject.value = ""; body.value = "";
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function remove(id: number) {
  await deleteTemplate(id);
  await reload();
}

onMounted(reload);
</script>

<template>
  <section data-testid="template-section">
    <div class="contacts-head">
      <h3>邮件模板（{{ templates.length }}）</h3>
      <button
        class="small"
        @click="adding = true"
      >
        新建模板
      </button>
    </div>
    <p
      v-if="error"
      class="error small"
    >
      {{ error }}
    </p>
    <div
      v-if="adding"
      class="panel"
    >
      <div class="contact-form">
        <input
          v-model="name"
          placeholder="模板名（如：首次触达）"
          class="input-country"
        >
        <input
          v-model="subject"
          placeholder="邮件主题（支持变量）"
          class="grow"
        >
      </div>
      <textarea
        v-model="body"
        rows="6"
        placeholder="邮件正文…&#10;Hi {contact_name},&#10;&#10;We noticed {company} imports {product}…&#10;&#10;Best,&#10;{sender_name}"
        data-testid="template-body"
      />
      <p class="muted small">
        {{ VAR_HINT }}
      </p>
      <div class="actions">
        <button
          class="small primary"
          :disabled="!name || !subject || !body"
          @click="submit"
        >
          保存模板
        </button>
        <button
          class="small ghost"
          @click="adding = false"
        >
          取消
        </button>
      </div>
    </div>
    <ul
      v-if="templates.length"
      class="contact-list"
    >
      <li
        v-for="t in templates"
        :key="t.id"
      >
        <strong>{{ t.name }}</strong>
        <span class="muted small"> {{ t.subject }}</span>
        <button
          class="small ghost"
          @click="remove(t.id)"
        >
          删除
        </button>
      </li>
    </ul>
    <p
      v-else
      class="muted small"
    >
      暂无模板——创建一个开始发信
    </p>
  </section>
</template>
