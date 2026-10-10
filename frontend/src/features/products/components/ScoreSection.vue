<script setup lang="ts">
import type { CompanyDetail } from "@/api/products";
import ReasonList from "./ReasonList.vue";
import ScoreSummary from "./ScoreSummary.vue";

defineProps<{
  score: NonNullable<CompanyDetail["scores"][number]>;
}>();
const emit = defineEmits<{ locate: [billId: number] }>();
</script>

<template>
  <section>
    <ScoreSummary :score="score" />
    <h2>得分理由</h2>
    <ReasonList
      :reasons="score.reasons"
      @locate="emit('locate', $event)"
    />
    <p
      v-if="score.suppliers.length"
      class="small muted"
    >
      供货方：{{ score.suppliers.join("；") }}
    </p>
  </section>
</template>
