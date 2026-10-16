<script setup lang="ts">
import { onMounted } from "vue";
import { RouterLink } from "vue-router";
import KitNav from "../components/KitNav.vue";
import { PAGE_ROUTE, useKitTasks } from "../composables/useKitTasks";

const { data, days, error, load, toggle } = useKitTasks();
onMounted(load);
</script>

<template>
  <div class="panel">
    <KitNav />
    <h1>今日任务台</h1>
    <p
      v-if="data"
      class="muted"
      data-testid="kit-progress"
    >
      今天是第 {{ data.today }} 天 · 已完成 {{ data.done_count }}/{{ data.total }}
    </p>
    <p
      v-if="error"
      class="error small"
    >
      {{ error }}
    </p>
    <section
      v-for="d in days"
      :key="d.day"
      class="kit-day"
      :class="{ current: data && d.day === data.today }"
    >
      <h3>第 {{ d.day }} 天</h3>
      <ul>
        <li
          v-for="t in d.tasks"
          :key="t.key"
        >
          <label>
            <input
              type="checkbox"
              :checked="t.done"
              :aria-label="t.title"
              @change="toggle(t)"
            >
            <span :class="{ done: t.done }">{{ t.title }}</span>
          </label>
          <RouterLink
            v-if="PAGE_ROUTE[t.page]"
            :to="PAGE_ROUTE[t.page]!"
            class="small"
          >
            去处理 →
          </RouterLink>
          <span
            v-else-if="t.page === 'external'"
            class="small muted"
          >站外操作</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.kit-day { border-left: 3px solid var(--line); padding: 4px 12px; margin: 8px 0; }
.kit-day.current { border-left-color: var(--marine); background: var(--marine-soft); }
.kit-day ul { list-style: none; padding: 0; margin: 4px 0; }
.kit-day li { display: flex; gap: 12px; align-items: center; padding: 3px 0; }
.done { text-decoration: line-through; color: var(--ink-soft); }
</style>
