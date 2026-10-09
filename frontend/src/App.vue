<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
</script>

<template>
  <header class="topbar">
    <RouterLink
      to="/"
      class="brand"
    >
      TrueOrder <span class="brand-sub">自家产品海外买家库</span>
    </RouterLink>
  </header>
  <main class="page">
    <RouterView />
  </main>
</template>
