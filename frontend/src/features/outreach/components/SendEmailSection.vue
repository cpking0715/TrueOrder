<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Opportunity } from "@/api/opportunities";
import type { Contact } from "@/api/contacts";
import { fetchTemplates, previewEmail, queueSend, type Template, type PreviewResult } from "@/api/outreach";

const props = defineProps<{ opportunity: Opportunity; contacts: Contact[] }>();
const emit = defineEmits<{ sent: [] }>();

const templates = ref<Template[]>([]);
const selectedTemplate = ref<number | null>(null);
const selectedContact = ref<number | null>(null);
const preview = ref<PreviewResult | null>(null);
const error = ref("");
const busy = ref(false);
const sent = ref(false);

const emailContacts = computed(() => props.contacts.filter((c) => c.email));

async function load() {
  try {
    templates.value = await fetchTemplates();
  } catch {
    templates.value = [];
  }
}

async function doPreview() {
  if (!selectedTemplate.value || !selectedContact.value) return;
  busy.value = true;
  error.value = "";
  preview.value = null;
  sent.value = false;
  try {
    preview.value = await previewEmail({
      template_id: selectedTemplate.value,
      opportunity_id: props.opportunity.opportunity_id,
      contact_id: selectedContact.value,
    });
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}

async function send() {
  if (!selectedTemplate.value || !selectedContact.value) return;
  busy.value = true;
  try {
    await queueSend(selectedTemplate.value, props.opportunity.opportunity_id, selectedContact.value);
    sent.value = true;
    emit("sent");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section
    id="drawer-email"
    data-testid="send-email-section"
  >
    <h3>发开发信</h3>
    <p
      v-if="!emailContacts.length"
      class="muted small"
    >
      该公司暂无带邮箱的联系人——先补全联系方式
    </p>
    <p
      v-else-if="!templates.length"
      class="muted small"
    >
      暂无邮件模板——在跟进看板页创建
    </p>
    <template v-else>
      <div class="filterbar">
        <select v-model.number="selectedContact">
          <option :value="null">
            选联系人
          </option>
          <option
            v-for="c in emailContacts"
            :key="c.contact_id"
            :value="c.contact_id"
          >
            {{ c.name || c.email }}（{{ c.email }}）
          </option>
        </select>
        <select v-model.number="selectedTemplate">
          <option :value="null">
            选模板
          </option>
          <option
            v-for="t in templates"
            :key="t.id"
            :value="t.id"
          >
            {{ t.name }}
          </option>
        </select>
        <button
          class="small"
          :disabled="!selectedTemplate || !selectedContact || busy"
          data-testid="preview-email"
          @click="doPreview"
        >
          {{ busy ? "生成中…" : "预览" }}
        </button>
      </div>

      <div
        v-if="preview"
        class="panel email-preview"
        data-testid="email-preview"
      >
        <p><strong>主题：</strong>{{ preview.subject }}</p>
        <pre class="email-body">{{ preview.body }}</pre>
        <p
          v-if="!preview.guards_ok"
          class="badge excluded"
        >
          {{ preview.guards_error }}
        </p>
        <button
          v-else
          class="small primary"
          :disabled="busy"
          data-testid="send-email"
          @click="send"
        >
          {{ busy ? "发送中…" : "确认发送" }}
        </button>
      </div>
      <p
        v-if="sent"
        class="small muted"
        data-testid="sent-hint"
      >
        已入队发送——worker 执行后可在消息日志查看状态
      </p>
      <p
        v-if="error"
        class="error small"
      >
        {{ error }}
      </p>
    </template>
  </section>
</template>

