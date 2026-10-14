<script setup lang="ts">
import { ref } from "vue";
import { discoverBuyers } from "@/api/products";

const props = defineProps<{ productId: number }>();
const hint = ref("");
const error = ref("");
const busy = ref(false);

async function go() {
  error.value = "";
  hint.value = "";
  busy.value = true;
  try {
    const result = await discoverBuyers(props.productId);
    hint.value = `意向线索发现已启动（任务 #${result.job_id}）。结果进「意向线索」潜在层（含个人/感兴趣对象），不升精准。`;
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <button
    class="small ghost"
    :disabled="busy"
    data-testid="discover-buyers"
    title="从品名发现可能感兴趣的对象（进口商、小买家、个人工作室等），写入「意向线索」；不升精准"
    @click="go"
  >
    {{ busy ? "启动中…" : "AI 发现意向线索" }}
  </button>
  <span
    v-if="hint"
    class="small muted"
    data-testid="discover-hint"
  >{{ hint }} <a href="#/jobs">查看进度</a></span>
  <span
    v-if="error"
    class="error small"
  >{{ error }}</span>
</template>
