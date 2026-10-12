<script setup lang="ts">
defineProps<{ title: string }>();
const emit = defineEmits<{ close: [] }>();

// 分区锚点：长抽屉的页内导航（与 drawer section 的 id 对应）
const NAV = [
  { id: "drawer-score", label: "得分" },
  { id: "drawer-bills", label: "提单" },
  { id: "drawer-website", label: "官网" },
  { id: "drawer-contacts", label: "联系人" },
];

function jumpTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
}
</script>

<template>
  <div class="drawer-head">
    <span class="drawer-title">{{ title }}</span>
    <nav class="drawer-nav">
      <a
        v-for="item in NAV"
        :key="item.id"
        :href="`#${item.id}`"
        class="bill-chip-link"
        @click.prevent="jumpTo(item.id)"
      >{{ item.label }}</a>
    </nav>
    <button
      class="small ghost"
      data-testid="drawer-close"
      @click="emit('close')"
    >
      关闭
    </button>
  </div>
</template>
