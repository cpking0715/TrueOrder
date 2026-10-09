<script setup lang="ts">
import type { Product } from "@/api/products";

defineProps<{ product: Product; audience: string }>();
const emit = defineEmits<{ "update:audience": [value: string] }>();

const buyerTypeLabel: Record<string, string> = {
  importer: "卖给进口商",
  factory: "卖给工厂",
  both: "两者都卖",
};
</script>

<template>
  <h1>{{ product.name }}</h1>
  <p class="muted">
    <span
      class="badge"
      :class="product.buyer_type"
    >{{ buyerTypeLabel[product.buyer_type] }}</span>
    <span
      v-for="hs in product.hs_codes"
      :key="hs.hs_code"
      class="badge"
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
    v-if="product.buyer_type === 'both'"
    class="filterbar"
  >
    <span class="muted">受众：</span>
    <button
      :class="{ primary: audience === 'importer' }"
      @click="emit('update:audience', 'importer')"
    >
      进口商视角
    </button>
    <button
      :class="{ primary: audience === 'factory' }"
      @click="emit('update:audience', 'factory')"
    >
      工厂视角
    </button>
  </div>
</template>
