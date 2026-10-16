<script setup lang="ts">
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { fetchKitProfiles, saveKitProfile, type KitProfile, type KitProfileIn } from "@/api/kit";
import { useAsync } from "@/composables/useAsync";
import KitNav from "../components/KitNav.vue";
import ProfileForm from "../components/ProfileForm.vue";

const products = ref<KitProfile[]>([]);
const editing = ref<number | null>(null);
const notice = ref("");
const { busy, error, run } = useAsync();

async function load() {
  products.value = (await run(fetchKitProfiles)) ?? products.value;
}

async function save(productId: number, payload: KitProfileIn) {
  const saved = await run(() => saveKitProfile(productId, payload));
  if (!saved) return;
  notice.value = `已保存「${saved.name}」`;
  editing.value = null;
  await load();
}

onMounted(load);
</script>

<template>
  <div class="panel">
    <KitNav />
    <h1>产品档案</h1>
    <p class="muted small">
      复用现有产品；新产品请先在 <RouterLink to="/">
        客户页
      </RouterLink> 用「填产品找客户」建好，再回来补档案。主推款最多 5 个。
    </p>
    <p
      v-if="error"
      class="error small"
    >
      {{ error }}
    </p>
    <p
      v-if="notice"
      class="small"
    >
      {{ notice }}
    </p>
    <p
      v-if="!products.length"
      class="muted"
    >
      还没有产品。
    </p>
    <article
      v-for="p in products"
      :key="p.product_id"
      class="kit-card"
      :data-testid="`kit-product-${p.product_id}`"
    >
      <header>
        <strong>{{ p.name }}</strong>
        <span class="code small">{{ p.code }}</span>
        <span
          v-if="p.featured"
          class="badge info"
        >主推</span>
        <span
          v-if="!p.has_profile"
          class="badge muted"
        >未建档案</span>
        <span
          v-else
          class="small muted"
        >MOQ {{ p.moq }} · 交期 {{ p.lead_time_days }} 天</span>
        <button
          type="button"
          @click="editing = editing === p.product_id ? null : p.product_id"
        >
          {{ editing === p.product_id ? "收起" : "编辑档案" }}
        </button>
      </header>
      <ProfileForm
        v-if="editing === p.product_id"
        :profile="p"
        :busy="busy"
        @save="(payload) => save(p.product_id, payload)"
      />
    </article>
  </div>
</template>

<style scoped>
.kit-card { border: 1px solid var(--line); border-radius: var(--radius); padding: 10px 12px; margin: 8px 0; }
.kit-card header { display: flex; gap: 10px; align-items: center; }
.kit-card header button { margin-left: auto; }
</style>
