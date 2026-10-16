<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { createKitDraft, fetchKitDrafts, type KitDraft } from "@/api/kit";
import { useAsync } from "@/composables/useAsync";
import DraftCard from "../components/DraftCard.vue";
import KitNav from "../components/KitNav.vue";
import { useKitPickers } from "../composables/useKitPickers";

const { buyers, readyProducts, loadPickers } = useKitPickers();
const drafts = ref<KitDraft[]>([]);
const form = reactive({ product_id: 0, company_id: 0, channel: "email" as "email" | "whatsapp" });
const { busy, error, run } = useAsync();
const canGenerate = computed(() => form.product_id > 0 && form.company_id > 0 && !busy.value);

async function load() {
  await run(async () => {
    await loadPickers();
    drafts.value = await fetchKitDrafts();
  });
}

async function generate() {
  const buyer = buyers.value.find((b) => b.company_id === form.company_id);
  const draft = await run(() =>
    createKitDraft({ ...form, contact_id: buyer?.contact_id ?? null }),
  );
  if (draft) drafts.value = [draft, ...drafts.value];
}

onMounted(load);
</script>

<template>
  <div class="panel">
    <KitNav />
    <h1>开发信工作台</h1>
    <p class="muted small">
      只生成草稿，复制后由你自己在邮箱或 WhatsApp 里发送；勿联系、抑制名单里的联系人不生成。
    </p>
    <div class="kit-compose">
      <select
        v-model.number="form.product_id"
        aria-label="产品"
      >
        <option :value="0">
          选择产品（需已建档案）
        </option>
        <option
          v-for="p in readyProducts"
          :key="p.product_id"
          :value="p.product_id"
        >
          {{ p.name }}
        </option>
      </select>
      <select
        v-model.number="form.company_id"
        aria-label="买家"
      >
        <option :value="0">
          选择买家
        </option>
        <option
          v-for="b in buyers"
          :key="b.company_id"
          :value="b.company_id"
        >
          {{ b.name }}（{{ b.country }}）
        </option>
      </select>
      <select
        v-model="form.channel"
        aria-label="渠道"
      >
        <option value="email">
          邮件
        </option>
        <option value="whatsapp">
          WhatsApp
        </option>
      </select>
      <button
        type="button"
        :disabled="!canGenerate"
        @click="generate"
      >
        生成草稿
      </button>
    </div>
    <p
      v-if="error"
      class="error small"
    >
      {{ error }}
    </p>
    <p
      v-if="!drafts.length"
      class="muted"
    >
      还没有草稿。
    </p>
    <DraftCard
      v-for="d in drafts"
      :key="d.id"
      :draft="d"
    />
  </div>
</template>

<style scoped>
.kit-compose { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
</style>
