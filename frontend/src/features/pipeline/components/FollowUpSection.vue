<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import TimelineList from "./TimelineList.vue";
import {
  STAGE_LABEL,
  addActivity,
  fetchTimeline,
  patchOpportunity,
  type Activity,
  type Opportunity,
  type Stage,
} from "@/api/opportunities";

const props = defineProps<{ opportunity: Opportunity }>();
const emit = defineEmits<{ changed: [] }>();

const timeline = ref<Activity[]>([]);
const error = ref("");
const busy = ref(false);
const noteKind = ref("note");
const noteSummary = ref("");
const noteIntent = ref("");

const stageOptions = computed(() => Object.entries(STAGE_LABEL));

async function reload() {
  try {
    timeline.value = await fetchTimeline(props.opportunity.opportunity_id);
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function changeStage(stage: Stage) {
  const payload: Parameters<typeof patchOpportunity>[1] = { stage };
  if (stage === "lost") {
    const reason = window.prompt?.("流失原因（必填）") ?? "";
    if (!reason.trim()) return;
    payload.closed_reason = reason.trim();
  }
  busy.value = true;
  try {
    await patchOpportunity(props.opportunity.opportunity_id, payload);
    emit("changed");
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}

async function submitActivity() {
  if (!noteSummary.value.trim()) return;
  busy.value = true;
  try {
    await addActivity(props.opportunity.opportunity_id, {
      kind: noteKind.value,
      summary: noteSummary.value.trim(),
      intent_after: noteIntent.value || undefined,
    });
    noteSummary.value = "";
    noteIntent.value = "";
    emit("changed");
    await reload();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}

onMounted(reload);
</script>

<template>
  <section
    id="drawer-followup"
    data-testid="followup-section"
  >
    <h3>跟进</h3>
    <div class="filterbar">
      <select
        :value="opportunity.stage"
        :disabled="busy"
        data-testid="followup-stage"
        @change="changeStage(($event.target as HTMLSelectElement).value as Stage)"
      >
        <option
          v-for="[value, label] in stageOptions"
          :key="value"
          :value="value"
        >
          {{ label }}
        </option>
      </select>
      <input
        type="date"
        :value="opportunity.next_follow_up_on ?? ''"
        title="下次跟进日期"
        @change="patchOpportunity(opportunity.opportunity_id, {
          next_follow_up_on: ($event.target as HTMLInputElement).value || undefined,
        }).then(() => emit('changed'))"
      >
    </div>
    <p
      v-if="opportunity.closed_reason"
      class="small muted"
    >
      流失原因：{{ opportunity.closed_reason }}
    </p>
    <div class="contact-form">
      <select v-model="noteKind">
        <option value="note">
          备注
        </option>
        <option value="call">
          电话
        </option>
        <option value="whatsapp">
          WhatsApp
        </option>
        <option value="email_out">
          发信
        </option>
        <option value="email_in">
          回信
        </option>
      </select>
      <input
        v-model="noteSummary"
        placeholder="一句话摘要"
        data-testid="activity-summary"
      >
      <input
        v-model="noteIntent"
        placeholder="意愿变化（选填：cold/warm/hot）"
        class="input-country"
      >
      <button
        class="small"
        :disabled="busy || !noteSummary.trim()"
        data-testid="activity-submit"
        @click="submitActivity"
      >
        记录
      </button>
    </div>
    <p
      v-if="error"
      class="error small"
      role="alert"
    >
      {{ error }}
    </p>
    <TimelineList :timeline="timeline" />
  </section>
</template>
