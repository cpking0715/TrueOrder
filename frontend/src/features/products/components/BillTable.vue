<script setup lang="ts">
import type { CompanyDetail } from "@/api/products";

defineProps<{ bills: CompanyDetail["bills"]; highlightId: number | null }>();
</script>

<template>
  <table
    class="grid"
    data-testid="drawer-bills"
  >
    <thead>
      <tr>
        <th>提单号</th>
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
        :id="`bill-row-${bill.bill_id}`"
        :key="bill.bill_id"
        :class="{ highlighted: highlightId === bill.bill_id }"
      >
        <td class="code small">
          {{ bill.bill_number || "—" }} <span class="muted">#{{ bill.bill_id }}</span>
        </td>
        <td class="code">
          {{ bill.arrival_date }}
        </td>
        <td class="code">
          {{ bill.hs_code || "—" }}
          <span
            v-if="bill.hs_suspect"
            class="badge excluded"
          >税号误码</span>
        </td>
        <td class="code">
          {{ bill.origin_country || "—" }}
        </td>
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

