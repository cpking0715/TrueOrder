<script setup lang="ts">
/** 出海包五页之间的页签导航。 */
import { RouterLink } from "vue-router";

const PAGES = [
  { to: "/kit", label: "今日任务" },
  { to: "/kit/products", label: "产品档案" },
  { to: "/kit/buyers", label: "买家线索" },
  { to: "/kit/drafts", label: "开发信" },
  { to: "/kit/inquiries", label: "询盘报价" },
];
</script>

<template>
  <div>
    <p class="eyebrow">
      出海包 v0.1 · 内部工具
    </p>
    <nav
      class="tabs"
      aria-label="出海包页面"
    >
      <RouterLink
        v-for="p in PAGES"
        :key="p.to"
        :to="p.to"
        class="kit-tab"
        exact-active-class="active"
      >
        {{ p.label }}
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.kit-tab { padding: 8px 14px; color: var(--ink-soft); text-decoration: none; border-bottom: 2px solid transparent; margin-bottom: -2px; }
.kit-tab.active { color: var(--marine-deep); border-bottom-color: var(--marine); font-weight: 600; }
</style>
