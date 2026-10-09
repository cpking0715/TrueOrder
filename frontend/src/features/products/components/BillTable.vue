<script setup lang="ts">
import type { CompanyDetail } from "@/api/products";

defineProps<{ bills: CompanyDetail["bills"] }>();
</script>

<template>
  <table
    class="grid"
    data-testid="drawer-bills"
  >
    <thead>
      <tr>
        <th>到港</th>
        <th>税号</th>
        <th>原产</th>
        <th>供货方</th>
        <th>货物描述</th>
        <th>港口</th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="bill in bills"
        :key="bill.bill_id"
      >
        <td>{{ bill.arrival_date }}</td>
        <td>
          {{ bill.hs_code || "—" }}
          <span
            v-if="bill.hs_suspect"
            class="badge excluded"
          >税号误码</span>
        </td>
        <td>{{ bill.origin_country || "—" }}</td>
        <td class="small">
          {{ bill.shipper || "—" }}
        </td>
        <td class="small">
          {{ bill.product_description || "—" }}
        </td>
        <td class="small">
          {{ bill.port || "—" }}
        </td>
      </tr>
    </tbody>
  </table>
</template>
