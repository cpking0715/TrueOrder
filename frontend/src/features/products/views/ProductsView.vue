<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import NoticeBanner from "@/components/NoticeBanner.vue";
import { fetchMeta, fetchProducts, type Meta, type Product } from "@/api/products";
import ProductCard from "../components/ProductCard.vue";
import ImportPanel from "../components/ImportPanel.vue";
import QuickStartForm from "../components/QuickStartForm.vue";

const router = useRouter();
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

function goDetail(product: Product) {
  void router.push(`/products/${product.product_id}`);
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
    <h1>填你的产品，找对应客户</h1>
    <p class="muted">
      填产品名称与 HS 税号，系统立即在已导入的提单库中匹配潜在客户与精准客户。
      提单数据来自你上传的授权 CSV（用下方数据导入面板）。
    </p>
    <QuickStartForm @created="goDetail" />
  </div>
  <div class="panel">
    <h2>我的产品</h2>
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
      还没有产品。在上方填一个产品即可开始，或导入产品 CSV。
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
