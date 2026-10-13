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
    hint.value = `AI 买家发现已启动（任务 #${result.job_id}）。worker 自动生成名单并补全联系方式。`;
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
    title="AI 从品名推断该行业真实进口商，自动补全联系方式（不消耗额度，不依赖提单数据）"
    @click="go"
  >
    {{ busy ? "启动中…" : "AI 发现买家" }}
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
