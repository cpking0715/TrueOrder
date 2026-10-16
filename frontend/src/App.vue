<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
</script>

<template>
  <div class="app-shell">
    <nav class="sidebar">
      <RouterLink
        to="/"
        class="brand"
      >
        <span class="brand-mark">TO</span>
        <span class="brand-name">TrueOrder</span>
      </RouterLink>
      <RouterLink
        to="/"
        class="nav-item"
        exact-active-class="active"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
        >
          <path
            d="M3 6L10 2L17 6V14L10 18L3 14V6Z"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <path
            d="M10 2V9M3 6L10 9L17 6"
            stroke="currentColor"
            stroke-width="1.5"
          />
        </svg>
        <span>客户</span>
      </RouterLink>
      <RouterLink
        to="/pipeline"
        class="nav-item"
        active-class="active"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
        >
          <rect
            x="2"
            y="3"
            width="4"
            height="14"
            rx="1"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <rect
            x="8"
            y="3"
            width="4"
            height="9"
            rx="1"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <rect
            x="14"
            y="3"
            width="4"
            height="6"
            rx="1"
            stroke="currentColor"
            stroke-width="1.5"
          />
        </svg>
        <span>跟进</span>
      </RouterLink>
      <RouterLink
        to="/jobs"
        class="nav-item"
        active-class="active"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
        >
          <circle
            cx="10"
            cy="10"
            r="7"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <path
            d="M10 6V10L13 12"
            stroke="currentColor"
            stroke-width="1.5"
          />
        </svg>
        <span>任务</span>
      </RouterLink>
      <RouterLink
        to="/kit"
        class="nav-item"
        active-class="active"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
        >
          <path
            d="M3 14L10 4L17 14H3Z"
            stroke="currentColor"
            stroke-width="1.5"
          />
          <path
            d="M2 17H18"
            stroke="currentColor"
            stroke-width="1.5"
          />
        </svg>
        <span>出海包</span>
      </RouterLink>
    </nav>
    <main class="page">
      <RouterView />
    </main>
  </div>
</template>
