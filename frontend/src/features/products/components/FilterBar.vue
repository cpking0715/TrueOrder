<script setup lang="ts">
import type { FilterState } from "../composables/useBuyerFilters";

defineProps<{ state: FilterState; total: number }>();
const emit = defineEmits<{
  "update:q": [value: string];
  "update:country": [value: string];
  "update:minShipments": [value: number | undefined];
  "update:order": [value: FilterState["order"]];
  changed: [];
}>();
</script>

<template>
  <div class="filterbar">
    <input
      class="grow"
      :value="state.q"
      placeholder="搜索公司名/地址（全文检索，支持 OR）"
      data-testid="filter-q"
      @input="emit('update:q', ($event.target as HTMLInputElement).value); emit('changed')"
    >
    <input
      :value="state.country"
      placeholder="国家（如 US）"
      style="width: 110px"
      data-testid="filter-country"
      @input="emit('update:country', ($event.target as HTMLInputElement).value); emit('changed')"
    >
    <select
      :value="state.minShipments"
      data-testid="filter-min"
      @change="emit('update:minShipments', Number(($event.target as HTMLSelectElement).value) || undefined); emit('changed')"
    >
      <option :value="undefined">
        最少票数不限
      </option>
      <option :value="2">
        ≥ 2 票
      </option>
      <option :value="3">
        ≥ 3 票
      </option>
      <option :value="5">
        ≥ 5 票
      </option>
    </select>
    <select
      :value="state.order"
      data-testid="filter-order"
      @change="emit('update:order', ($event.target as HTMLSelectElement).value as FilterState['order']); emit('changed')"
    >
      <option value="shipments">
        按票数排序
      </option>
      <option value="last_arrival">
        按最近到港排序
      </option>
      <option value="name">
        按名称排序
      </option>
    </select>
    <span class="muted">共 {{ total }} 家</span>
  </div>
</template>
