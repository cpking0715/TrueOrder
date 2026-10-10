<script setup lang="ts">
import type { Buyer } from "@/api/products";

defineProps<{ buyers: Buyer[]; loading: boolean }>();
const emit = defineEmits<{ select: [buyer: Buyer] }>();

function reasonPreview(buyer: Buyer): string {
  return buyer.reasons
    .slice(0, 2)
    .map((r) => r.text)
    .join("；");
}
</script>

<template>
  <div
    v-if="loading"
    class="empty"
  >
    加载中…
  </div>
  <div
    v-else-if="buyers.length === 0"
    class="empty"
    data-testid="buyers-empty"
  >
    当前筛选下没有公司。
  </div>
  <div
    v-else
    class="table-scroll"
  >
    <table
      class="grid"
      data-testid="buyers-table"
    >
      <thead>
        <tr>
          <th>公司</th>
          <th>国家/城市</th>
          <th>票数</th>
          <th>最近到港</th>
          <th>供货方</th>
          <th>得分理由（摘要）</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="buyer in buyers"
          :key="buyer.company_id"
          :class="['clickable', 'rail-' + buyer.tier]"
          tabindex="0"
          role="button"
          :aria-label="`查看 ${buyer.name} 的提单证据`"
          @click="emit('select', buyer)"
          @keydown.enter.prevent="emit('select', buyer)"
          @keydown.space.prevent="emit('select', buyer)"
        >
          <td>
            <strong>{{ buyer.name }}</strong>
            <span
              v-if="buyer.same_name_conflict"
              class="badge conflict"
              title="同名不同城市线索，未自动合并"
            >
              同名冲突
            </span>
          </td>
          <td class="code">
            {{ buyer.country }}<span v-if="buyer.city"> · {{ buyer.city }}</span>
          </td>
          <td class="num">
            {{ buyer.shipments }}
          </td>
          <td class="code">
            {{ buyer.last_arrival ?? "—" }}
          </td>
          <td class="small">
            {{ buyer.suppliers.join("；") || "—" }}
          </td>
          <td class="small muted">
            {{ reasonPreview(buyer) }}
            <span
              v-if="buyer.exclusion_code"
              class="badge excluded"
            >{{ buyer.exclusion_code }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
