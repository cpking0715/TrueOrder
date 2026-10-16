<script setup lang="ts">
/** 一封草稿：复制、导出 txt、第 3/7 天跟进提醒。只生成，不发送。 */
import { ref } from "vue";
import { draftExportUrl, type KitDraft } from "@/api/kit";

const props = defineProps<{ draft: KitDraft }>();
const copied = ref(false);

async function copy() {
  const text = props.draft.subject ? `${props.draft.subject}\n\n${props.draft.body}` : props.draft.body;
  await navigator.clipboard?.writeText(text);
  copied.value = true;
}
</script>

<template>
  <article
    class="draft-card"
    :data-testid="`kit-draft-${draft.id}`"
  >
    <header class="small">
      <strong>{{ draft.company_name }}</strong>
      <span class="badge muted">{{ draft.channel === "email" ? "邮件" : "WhatsApp" }}</span>
      <span class="badge info">{{ draft.source === "llm" ? "AI 生成" : "模板" }}</span>
      <span class="muted">跟进：{{ draft.follow_up_on.join(" / ") }}</span>
      <span
        v-if="draft.next_follow_up"
        class="badge warn"
      >下次 {{ draft.next_follow_up }}</span>
    </header>
    <p
      v-if="draft.subject"
      class="subject"
    >
      {{ draft.subject }}
    </p>
    <pre class="body">{{ draft.body }}</pre>
    <div class="actions">
      <button
        type="button"
        @click="copy"
      >
        {{ copied ? "已复制" : "复制" }}
      </button>
      <a
        :href="draftExportUrl(draft.id)"
        download
      >导出 txt</a>
    </div>
  </article>
</template>

<style scoped>
.draft-card { border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 12px; margin: 8px 0; }
.draft-card header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.subject { font-weight: 600; margin: 6px 0; }
.body { white-space: pre-wrap; font-family: inherit; font-size: 13px; background: var(--paper); padding: 8px; border-radius: 6px; }
.actions { display: flex; gap: 12px; align-items: center; }
</style>
