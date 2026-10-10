<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { confirmWebsite, patchCompanyWebsite } from "@/api/contacts";

const props = defineProps<{
  companyId: number;
  website?: string | null;
  confirmed?: boolean;
  confidence?: string | null;
}>();

const CONFIDENCE_LABEL: Record<string, string> = {
  high: "高置信",
  medium: "中置信候选",
  low: "低置信候选",
};
const confidenceLabel = computed(() =>
  props.confidence ? CONFIDENCE_LABEL[props.confidence] ?? props.confidence : ""
);
const emit = defineEmits<{ confirmed: [] }>();

const editing = ref(false);
const draft = ref("");
const confirmedDraft = ref(false);
const error = ref("");
const current = ref(props.website);
const currentConfirmed = ref(Boolean(props.confirmed));

watch(
  () => [props.website, props.confirmed] as const,
  ([w, c]) => {
    current.value = w;
    currentConfirmed.value = Boolean(c);
  },
);

function startEdit() {
  draft.value = current.value ?? "";
  confirmedDraft.value = currentConfirmed.value;
  editing.value = true;
}

async function save() {
  error.value = "";
  try {
    const result = await patchCompanyWebsite(props.companyId, {
      website: draft.value.trim(),
      website_confirmed: confirmedDraft.value,
    });
    current.value = result.website;
    currentConfirmed.value = result.website_confirmed;
    editing.value = false;
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function confirm() {
  error.value = "";
  try {
    const result = await confirmWebsite(props.companyId);
    currentConfirmed.value = result.website_confirmed;
    emit("confirmed");
  } catch (e) {
    error.value = (e as Error).message;
  }
}
</script>

<template>
  <p
    class="small website-field"
    data-testid="website-field"
  >
    <template v-if="!editing">
      官网：
      <a
        v-if="current"
        :href="current.startsWith('http') ? current : `https://${current}`"
        target="_blank"
        rel="noopener"
      >{{ current }}</a>
      <span
        v-else
        class="muted"
      >未填写</span>
      <span
        v-if="current && currentConfirmed"
        class="badge precise"
      >已确认</span>
      <span
        v-else-if="current && confidenceLabel"
        class="badge potential"
        :title="`补全服务返回的候选（${confidenceLabel}），确认后才用于查联系人`"
      >{{ confidenceLabel }}</span>
      <button
        v-if="current && !currentConfirmed"
        class="small"
        data-testid="confirm-website"
        @click="confirm"
      >
        确认是官网
      </button>
      <button
        class="small ghost"
        data-testid="edit-website"
        @click="startEdit"
      >
        编辑
      </button>
    </template>
    <template v-else>
      <input
        v-model="draft"
        placeholder="https://example.com"
        aria-label="公司官网"
        data-testid="website-input"
      >
      <label class="small">
        <input
          v-model="confirmedDraft"
          type="checkbox"
        >
        已人工确认
      </label>
      <button
        class="small"
        data-testid="save-website"
        @click="save"
      >
        保存
      </button>
      <button
        class="small ghost"
        @click="editing = false"
      >
        取消
      </button>
      <span
        v-if="error"
        class="error"
      >{{ error }}</span>
    </template>
  </p>
</template>
