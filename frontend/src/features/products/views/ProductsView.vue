<script setup lang="ts">
import { onMounted, ref } from "vue";
import NoticeBanner from "@/components/NoticeBanner.vue";
import { fetchMeta, fetchProducts, type Meta, type Product } from "@/api/products";
import ProductCard from "../components/ProductCard.vue";
import ImportPanel from "../components/ImportPanel.vue";

const meta = ref<Meta | null>(null);
const products = ref<Product[]>([]);
const error = ref("");

async function reload() {
  try {
    products.value = await fetchProducts();
  } catch (e) {
    error.value = `加载产品失败：${(e as Error).message}`;
  }
}

onMounted(async () => {
  try {
    meta.value = await fetchMeta();
  } catch {
    meta.value = null;
  }
  await reload();
});
</script>

<template>
  <NoticeBanner
    v-if="meta?.sample_mode"
    :notice="meta.sample_notice"
  />
  <div class="panel">
    <h1>自家产品</h1>
    <p class="muted">
      点进产品查看该产品的海外潜在客户与精准客户。
    </p>
    <p
      v-if="error"
      class="badge excluded"
    >
      {{ error }}
    </p>
    <div
      v-if="products.length === 0 && !error"
      class="empty"
    >
      还没有产品。先用下方导入产品 CSV，或运行 uv run python -m app.bootstrap。
    </div>
    <div class="cards">
      <ProductCard
        v-for="product in products"
        :key="product.product_id"
        :product="product"
      />
    </div>
  </div>
  <ImportPanel @imported="reload" />
</template>
