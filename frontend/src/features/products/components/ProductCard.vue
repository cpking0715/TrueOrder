<script setup lang="ts">
import type { Product } from "@/api/products";

const props = defineProps<{ product: Product }>();

const buyerTypeLabel: Record<string, string> = {
  importer: "卖给进口商",
  factory: "卖给工厂",
  both: "两者都卖",
};

function countOf(tier: string): number {
  return props.product.counts?.[tier] ?? 0;
}
</script>

<template>
  <RouterLink
    :to="{ name: 'product-detail', params: { id: product.product_id } }"
    class="card"
    style="display: block"
  >
    <h3>{{ product.name }}</h3>
    <div>
      <span
        class="badge"
        :class="product.buyer_type"
      >{{ buyerTypeLabel[product.buyer_type] }}</span>
      <span
        v-for="hs in product.hs_codes"
        :key="hs.hs_code + hs.audience"
        class="badge hs"
      >HS {{ hs.hs_code }}</span>
    </div>
    <p class="muted small">
      {{ product.description }}
    </p>
    <p
      v-for="hs in product.hs_codes"
      :key="'note' + hs.hs_code"
      class="muted small"
    >
      {{ hs.note }}
    </p>
    <div class="counts">
      <span><span class="num potential">{{ countOf("potential") }}</span> 潜在</span>
      <span><span class="num go">{{ countOf("precise") }}</span> 精准</span>
      <span><span class="num stamp">{{ countOf("excluded") }}</span> 排除</span>
    </div>
  </RouterLink>
</template>
