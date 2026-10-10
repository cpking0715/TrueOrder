<script setup lang="ts">
defineProps<{ busy: boolean; adding: boolean }>();
const emit = defineEmits<{
  find: [];
  crawl: [];
  add: [];
}>();
</script>

<template>
  <button
    class="small primary"
    :disabled="busy"
    data-testid="find-contacts"
    title="按官网域名/公司名调用补全服务（消耗每日额度）"
    @click="emit('find')"
  >
    {{ busy ? "入队中…" : "补全联系人" }}
  </button>
  <button
    class="small ghost"
    :disabled="busy"
    data-testid="crawl-website"
    title="抓取该企业官网公开页上的邮箱与电话（不消耗补全额度）"
    @click="emit('crawl')"
  >
    抓取官网
  </button>
  <button
    v-if="!adding"
    class="small ghost"
    data-testid="add-contact"
    @click="emit('add')"
  >
    新增联系人
  </button>
</template>
