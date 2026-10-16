<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { fetchKitBuyers, importKitBuyers, patchKitBuyer, type KitBuyer, type KitBuyerImport } from "@/api/kit";
import { useAsync } from "@/composables/useAsync";
import KitNav from "../components/KitNav.vue";

const STAGES = ["new", "contacted", "replied", "inquiry"];
const STAGE_LABEL: Record<string, string> = { new: "新线索", contacted: "已联系", replied: "已回复", inquiry: "有询盘" };
const CHANNELS = ["", "email", "whatsapp", "linkedin", "trade_show", "website", "other"];

const buyers = ref<KitBuyer[]>([]);
const summary = ref<KitBuyerImport | null>(null);
const filters = reactive({ country: "", channel: "", stage: "" });
const { busy, error, run } = useAsync();

async function load() {
  buyers.value = (await run(() => fetchKitBuyers({ ...filters }))) ?? buyers.value;
}

async function onFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  summary.value = (await run(() => importKitBuyers(file))) ?? null;
  await load();
}

async function setStage(b: KitBuyer, stage: string) {
  if (await run(() => patchKitBuyer(b.company_id, { stage }).then(() => true))) b.stage = stage;
}

onMounted(load);
</script>

<template>
  <div class="panel">
    <KitNav />
    <h1>买家线索库</h1>
    <p class="muted small">
      CSV 表头：company_name,country,contact_name,email,phone,channel,stage。文件内去重、邮箱格式校验；只入库，不发信、不调用补全。
    </p>
    <label class="small">导入 CSV <input
      type="file"
      accept=".csv,text/csv"
      :disabled="busy"
      data-testid="kit-buyer-file"
      @change="onFile"
    ></label>
    <p
      v-if="summary"
      class="small"
      data-testid="kit-import-summary"
    >
      新增 {{ summary.buyers_tagged }} 家，已在库 {{ summary.already_in_library }}，文件内重复 {{ summary.duplicates_in_file }}，联系人 +{{ summary.contacts_added }}，错误 {{ summary.errors.length }} 行
    </p>
    <ul
      v-if="summary?.errors.length"
      class="error small"
    >
      <li
        v-for="e in summary.errors"
        :key="e"
      >
        {{ e }}
      </li>
    </ul>
    <p
      v-if="error"
      class="error small"
    >
      {{ error }}
    </p>
    <div class="kit-filters">
      <input
        v-model="filters.country"
        placeholder="国家（如 US）"
        aria-label="国家"
        @change="load"
      >
      <select
        v-model="filters.channel"
        aria-label="渠道"
        @change="load"
      >
        <option
          v-for="c in CHANNELS"
          :key="c"
          :value="c"
        >
          {{ c || "全部渠道" }}
        </option>
      </select>
      <select
        v-model="filters.stage"
        aria-label="阶段"
        @change="load"
      >
        <option value="">
          全部阶段
        </option>
        <option
          v-for="s in STAGES"
          :key="s"
          :value="s"
        >
          {{ STAGE_LABEL[s] }}
        </option>
      </select>
      <span class="small muted">共 {{ buyers.length }} 家</span>
    </div>
    <table class="kit-table">
      <thead><tr><th>企业</th><th>国家</th><th>联系人</th><th>渠道</th><th>阶段</th></tr></thead>
      <tbody>
        <tr
          v-for="b in buyers"
          :key="b.company_id"
        >
          <td>{{ b.name }}</td>
          <td>{{ b.country }}</td>
          <td>{{ b.contact_name }} <span class="small muted">{{ b.email }}</span></td>
          <td>{{ b.channel }}</td>
          <td>
            <select
              :value="b.stage"
              :aria-label="`${b.name} 阶段`"
              @change="setStage(b, ($event.target as HTMLSelectElement).value)"
            >
              <option
                v-for="s in STAGES"
                :key="s"
                :value="s"
              >
                {{ STAGE_LABEL[s] }}
              </option>
            </select>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.kit-filters { display: flex; gap: 8px; align-items: center; margin: 12px 0; }
.kit-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.kit-table th, .kit-table td { text-align: left; padding: 6px; border-bottom: 1px solid var(--line); }
</style>
