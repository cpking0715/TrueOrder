<script setup lang="ts">
/** 产品档案表单：图片链接、规格、MOQ、交期、卖点（每行一条）、是否主推。 */
import { reactive } from "vue";
import type { KitProfile, KitProfileIn } from "@/api/kit";

const props = defineProps<{ profile: KitProfile; busy: boolean }>();
const emit = defineEmits<{ save: [payload: KitProfileIn] }>();

const form = reactive({
  image_url: props.profile.image_url,
  specs: props.profile.specs,
  moq: props.profile.moq || 100,
  lead_time_days: props.profile.lead_time_days || 30,
  points: props.profile.selling_points.join("\n"),
  featured: props.profile.has_profile ? props.profile.featured : true,
});

function submit() {
  emit("save", {
    image_url: form.image_url.trim(),
    specs: form.specs.trim(),
    moq: Number(form.moq),
    lead_time_days: Number(form.lead_time_days),
    selling_points: form.points.split("\n").map((s) => s.trim()).filter(Boolean),
    featured: form.featured,
  });
}
</script>

<template>
  <form
    class="kit-form"
    @submit.prevent="submit"
  >
    <label>图片链接 <input
      v-model="form.image_url"
      placeholder="https://..."
    ></label>
    <label>规格 <input
      v-model="form.specs"
      placeholder="尺码/面料/认证"
    ></label>
    <label>MOQ <input
      v-model.number="form.moq"
      type="number"
      min="1"
    ></label>
    <label>交期（天） <input
      v-model.number="form.lead_time_days"
      type="number"
      min="1"
    ></label>
    <label>卖点（每行一条，最多 5 条） <textarea
      v-model="form.points"
      rows="3"
    /></label>
    <label class="inline"><input
      v-model="form.featured"
      type="checkbox"
    > 主推款（最多 5 个）</label>
    <button
      type="submit"
      :disabled="busy"
    >
      保存档案
    </button>
  </form>
</template>

<style scoped>
.kit-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 16px; margin-top: 8px; }
.kit-form label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }
.kit-form label.inline { flex-direction: row; align-items: center; }
</style>
