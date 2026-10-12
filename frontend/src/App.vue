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
    <nav class="topnav">
      <RouterLink
        to="/pipeline"
        class="topnav-link"
      >
        跟进
      </RouterLink>
      <RouterLink
        to="/jobs"
        class="topnav-link"
      >
        任务
      </RouterLink>
    </nav>
  </header>
  <main class="page">
    <RouterView />
  </main>
</template>
