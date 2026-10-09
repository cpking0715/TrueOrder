import { createRouter, createWebHashHistory } from "vue-router";
import ProductsView from "@/features/products/views/ProductsView.vue";
import ProductDetailView from "@/features/products/views/ProductDetailView.vue";

export const router = createRouter({
  // hash 路由：后端静态托管时无需 SPA 回退
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "products", component: ProductsView },
    { path: "/products/:id", name: "product-detail", component: ProductDetailView },
  ],
});
