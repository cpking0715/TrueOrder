<script setup lang="ts">
import type { Buyer } from "@/api/products";
import { STAGE_LABEL } from "@/api/opportunities";

defineProps<{
  buyers: Buyer[];
  loading: boolean;
  followStages?: Record<number, string>;  // company_id → 当前阶段（已加入跟进）
}>();
const emit = defineEmits<{ select: [buyer: Buyer]; followUp: [buyer: Buyer] }>();

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
    当前筛选下没有公司——换个页签或放宽筛选试试。
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
          <th>跟进</th>
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
          <td>
            <span
              v-if="followStages?.[buyer.company_id]"
              class="badge potential"
            >{{ STAGE_LABEL[followStages[buyer.company_id] as keyof typeof STAGE_LABEL] }}</span>
            <button
              v-else
              class="small ghost"
              :data-testid="`follow-up-${buyer.company_id}`"
              title="加入跟进管道，在跟进看板管理阶段与提醒"
              @click.stop="emit('followUp', buyer)"
            >
              加入跟进
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
