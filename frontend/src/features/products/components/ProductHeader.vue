<script setup lang="ts">
import { computed } from "vue";
import type { Product } from "@/api/products";

const props = defineProps<{ product: Product; audience: string }>();
const emit = defineEmits<{ "update:audience": [value: string] }>();

const buyerTypeLabel: Record<string, string> = {
  importer: "卖给进口商",
  factory: "卖给工厂",
  both: "两者都卖",
};

const audienceLabel: Record<string, string> = {
  importer: "进口商视角",
  factory: "工厂视角",
  lead: "意向线索",
};

/** 提单受众随买家类型；意向线索始终可选（AI 发现 / 跟进等非提单来源）。 */
const billAudiences = computed(() => {
  if (props.product.buyer_type === "both") return ["importer", "factory"] as const;
  if (props.product.buyer_type === "factory") return ["factory"] as const;
  return ["importer"] as const;
});

const eyebrow = computed(() => {
  if (props.audience === "lead") return "意向线索 · INTERESTED LEADS";
  if (props.audience === "factory") return "FACTORY BUYERS";
  return "IMPORTERS";
});
</script>

<template>
  <p class="eyebrow">
    HS {{ product.hs_codes.map((h) => h.hs_code).join(" / ") || "—" }} · {{ eyebrow }}
  </p>
  <h1>{{ product.name }}</h1>
  <p class="muted">
    <span
      class="badge"
      :class="product.buyer_type"
    >{{ buyerTypeLabel[product.buyer_type] }}</span>
    <span
      v-for="hs in product.hs_codes"
      :key="hs.hs_code"
      class="badge hs"
    >
      HS {{ hs.hs_code }}
    </span>
  </p>
  <p class="muted small">
    {{ product.description }}
  </p>
  <p
    v-for="hs in product.hs_codes"
    :key="'n' + hs.hs_code"
    class="muted small"
  >
    {{ hs.note }}
  </p>
  <div
    class="filterbar"
    data-testid="audience-switch"
  >
    <span class="muted">受众：</span>
    <button
      v-for="a in billAudiences"
      :key="a"
      :class="{ primary: audience === a }"
      :data-testid="`audience-${a}`"
      @click="emit('update:audience', a)"
    >
      {{ audienceLabel[a] }}
    </button>
    <button
      :class="{ primary: audience === 'lead' }"
      data-testid="audience-lead"
      title="AI 发现、手动跟进等非提单来源；含个人/感兴趣对象；不升精准"
      @click="emit('update:audience', 'lead')"
    >
      意向线索
    </button>
  </div>
</template>
