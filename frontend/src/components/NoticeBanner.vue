<script setup lang="ts">
defineProps<{ notice: string }>();
</script>

<template>
  <div
    class="notice"
    role="note"
    data-testid="sample-notice"
  >
    {{ notice }}
  </div>
</template>
