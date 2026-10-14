import { createRouter, createWebHashHistory } from "vue-router";

export const router = createRouter({
  // hash 路由：后端静态托管时无需 SPA 回退
  history: createWebHashHistory(),
  routes: [
    {
      path: "/",
      name: "products",
      component: () => import("@/features/products/views/ProductsView.vue"),
    },
    {
      path: "/products/:id",
      name: "product-detail",
      component: () => import("@/features/products/views/ProductDetailView.vue"),
    },
    {
      path: "/jobs",
      name: "jobs",
      component: () => import("@/features/jobs/views/JobsView.vue"),
    },
    {
      path: "/pipeline",
      name: "pipeline",
      component: () => import("@/features/pipeline/views/PipelineView.vue"),
    },
  ],
});
