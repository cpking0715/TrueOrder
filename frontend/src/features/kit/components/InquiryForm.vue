<script setup lang="ts">
/** 登记询盘：买家 + 产品 + 数量 + 单价 + 币种 + 备注。 */
import { reactive } from "vue";
import type { KitBuyer, KitInquiryIn, KitProfile } from "@/api/kit";

defineProps<{ buyers: KitBuyer[]; products: KitProfile[]; busy: boolean }>();
const emit = defineEmits<{ submit: [payload: KitInquiryIn] }>();
const form = reactive({ company_id: 0, product_id: 0, quantity: 100, unit_price: "", currency: "USD", note: "" });

function submit() {
  emit("submit", { ...form, quantity: Number(form.quantity), unit_price: String(form.unit_price) });
}
</script>

<template>
  <form
    class="inq-form"
    @submit.prevent="submit"
  >
    <select
      v-model.number="form.company_id"
      aria-label="询盘买家"
    >
      <option :value="0">
        选择买家
      </option>
      <option
        v-for="b in buyers"
        :key="b.company_id"
        :value="b.company_id"
      >
        {{ b.name }}
      </option>
    </select>
    <select
      v-model.number="form.product_id"
      aria-label="询盘产品"
    >
      <option :value="0">
        选择产品
      </option>
      <option
        v-for="p in products"
        :key="p.product_id"
        :value="p.product_id"
      >
        {{ p.name }}
      </option>
    </select>
    <input
      v-model.number="form.quantity"
      type="number"
      min="1"
      aria-label="数量"
    >
    <input
      v-model="form.unit_price"
      placeholder="单价"
      aria-label="单价"
    >
    <input
      v-model="form.currency"
      maxlength="3"
      aria-label="币种"
    >
    <input
      v-model="form.note"
      placeholder="备注（看样/问价/要目录）"
      aria-label="备注"
    >
    <button
      type="submit"
      :disabled="busy || !form.company_id || !form.product_id"
    >
      登记询盘
    </button>
  </form>
</template>

<style scoped>
.inq-form { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
.inq-form input { width: 120px; }
</style>
