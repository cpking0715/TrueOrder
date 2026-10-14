<script setup lang="ts">
defineProps<{ audience?: string }>();
</script>

<template>
  <p
    v-if="audience === 'lead'"
    class="alert"
    data-testid="no-bills-hint"
  >
    「意向线索」来自 AI 发现或手动跟进，不依赖税号提单。点上方「AI 发现意向线索」可扩充名单；批量发信前请核对来源与合规。
  </p>
  <p
    v-else
    class="alert"
    data-testid="no-bills-hint"
  >
    库里还没有该税号的提单。两条路：到
    <RouterLink to="/">
      首页底部的「导入提单 CSV」
    </RouterLink>
    导入授权数据；或切到「意向线索」用 AI 从品名捞可能感兴趣的对象（不升精准）。
  </p>
</template>
