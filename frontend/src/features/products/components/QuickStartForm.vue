<script setup lang="ts">
import { computed, ref } from "vue";
import { createProduct, type Product } from "@/api/products";

const emit = defineEmits<{ created: [product: Product] }>();

const name = ref("");
const hsCode = ref("");
const buyerType = ref<"importer" | "factory" | "both">("importer");
const buyerKeywords = ref("");
const peerKeywords = ref("");
const error = ref("");
const submitting = ref(false);

const AUDIENCE_OPTIONS = [
  { value: "importer", label: "海外进口商/批发商（卖成品的）" },
  { value: "factory", label: "海外工厂（卖原料/设备的）" },
  { value: "both", label: "两类客户都找" },
] as const;

const DEFAULT_KEYWORDS: Record<string, string> = {
  importer: "IMPORT;TRADING;WHOLESALE;DISTRIBUT",
  factory: "MANUFACTUR;MILL;FACTORY;INDUSTRIES",
};
const keywordPlaceholder = computed(() => {
  if (buyerType.value === "both") {
    return `留空自动使用：${DEFAULT_KEYWORDS.importer};${DEFAULT_KEYWORDS.factory}`;
  }
  return `留空自动使用：${DEFAULT_KEYWORDS[buyerType.value]}`;
});

function splitKeywords(text: string): string[] {
  return [...new Set(
    text.replace(/[,，]/g, ";").split(";").map((kw) => kw.trim().toUpperCase()).filter(Boolean),
  )];
}

async function submit() {
  error.value = "";
  if (!name.value.trim()) {
    error.value = "请填写产品名称";
    return;
  }
  const hs = hsCode.value.trim();
  // 与后端 is_valid_hs 对齐：6-10 位纯数字，且前 6 位不得全零（0000001 也是误码）
  if (!/^\d{6,10}$/.test(hs) || hs.slice(0, 6) === "000000") {
    error.value = "税号需为 6-10 位数字（不能全零），如 620462";
    return;
  }
  submitting.value = true;
  try {
    const product = await createProduct({
      name: name.value.trim(),
      hs_code: hsCode.value.trim(),
      buyer_type: buyerType.value,
      description: "",
      buyer_keywords: splitKeywords(buyerKeywords.value),
      peer_keywords: splitKeywords(peerKeywords.value),
    });
    emit("created", product);
  } catch (e) {
    error.value = `创建失败：${(e as Error).message}`;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <form
    class="quickstart"
    data-testid="quickstart-form"
    @submit.prevent="submit"
  >
    <div class="strip">
      <span class="strip-code">Manifest Search</span>
      <span class="strip-title">授权提单库检索</span>
    </div>
    <div class="fields">
      <label>
        产品名称
        <input
          v-model="name"
          placeholder="如：女士棉质长裤"
          data-testid="quickstart-name"
        >
      </label>
      <label class="hs-input">
        HS 税号
        <input
          v-model="hsCode"
          inputmode="numeric"
          placeholder="620462"
          data-testid="quickstart-hs"
        >
      </label>
      <label>
        卖给谁
        <select
          v-model="buyerType"
          data-testid="quickstart-audience"
        >
          <option
            v-for="opt in AUDIENCE_OPTIONS"
            :key="opt.value"
            :value="opt.value"
          >
            {{ opt.label }}
          </option>
        </select>
      </label>
    </div>
    <div class="fields">
      <label class="grow">
        买家行业词（选填）
        <input
          v-model="buyerKeywords"
          :placeholder="keywordPlaceholder"
          data-testid="quickstart-buyer-kw"
        >
      </label>
      <label>
        同行行业词（选填）
        <input
          v-model="peerKeywords"
          placeholder="如：GARMENT FACTORY，用于排除同行海外公司"
          data-testid="quickstart-peer-kw"
        >
      </label>
    </div>
    <p
      v-if="error"
      class="badge excluded"
      role="alert"
    >
      {{ error }}
    </p>
    <div class="actions">
      <button
        type="submit"
        class="primary"
        :disabled="submitting"
      >
        {{ submitting ? "正在匹配客户…" : "找客户" }}
      </button>
      <span class="muted">提交后立即在已导入的提单库中匹配潜在/精准客户</span>
    </div>
  </form>
</template>
