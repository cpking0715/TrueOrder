<script setup lang="ts">
import { ref, watch } from "vue";
import { patchCompanyWebsite } from "@/api/contacts";

const props = defineProps<{
  companyId: number;
  website?: string | null;
  confirmed?: boolean;
}>();

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
        :href="current"
        target="_blank"
        rel="noopener"
      >{{ current }}</a>
      <span
        v-else
        class="muted"
      >未填写</span>
      <span
        v-if="current && currentConfirmed"
        class="badge"
      >已确认</span>
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
