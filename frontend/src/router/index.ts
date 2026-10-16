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
    {
      path: "/kit",
      name: "kit-today",
      component: () => import("@/features/kit/views/KitTodayView.vue"),
    },
    {
      path: "/kit/products",
      name: "kit-products",
      component: () => import("@/features/kit/views/KitProductsView.vue"),
    },
    {
      path: "/kit/buyers",
      name: "kit-buyers",
      component: () => import("@/features/kit/views/KitBuyersView.vue"),
    },
    {
      path: "/kit/drafts",
      name: "kit-drafts",
      component: () => import("@/features/kit/views/KitDraftsView.vue"),
    },
    {
      path: "/kit/inquiries",
      name: "kit-inquiries",
      component: () => import("@/features/kit/views/KitInquiriesView.vue"),
    },
  ],
});
