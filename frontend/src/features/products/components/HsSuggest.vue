<script setup lang="ts">
import { ref } from "vue";

const props = defineProps<{ initialKeyword?: string }>();
const emit = defineEmits<{ pick: [hsCode: string] }>();

const open = ref(false);
const keyword = ref(props.initialKeyword ?? "");
const items = ref<Array<{ hs_code: string; shipments: number; sample_description: string }>>([]);
const busy = ref(false);
const error = ref("");

async function search() {
  if (keyword.value.trim().length < 2) {
    error.value = "关键词至少 2 个字符";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    const response = await fetch(
      `/api/hs/suggest?q=${encodeURIComponent(keyword.value.trim())}`,
    );
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.detail ?? `${response.status}`);
    }
    items.value = await response.json();
    if (!items.value.length) error.value = "库里没有匹配的品名——先导入提单数据，或换个说法（英文品名最准）";
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}

function pick(hs: string) {
  emit("pick", hs);
  open.value = false;
}
</script>

<template>
  <a
    href="#"
    class="small muted"
    data-testid="hs-suggest-open"
    @click.prevent="open = true"
  >不知道税号？按品名查</a>
  <div
    v-if="open"
    class="hs-suggest"
    data-testid="hs-suggest"
  >
    <div class="contact-form">
      <input
        v-model="keyword"
        placeholder="品名关键词（英文最准，如 COTTON TROUSERS）"
        data-testid="hs-suggest-keyword"
        @keydown.enter.prevent="search"
      >
      <button
        class="small"
        :disabled="busy"
        data-testid="hs-suggest-search"
        @click="search"
      >
        {{ busy ? "查询中…" : "查税号" }}
      </button>
      <button
        class="small ghost"
        @click="open = false"
      >
        收起
      </button>
    </div>
    <p
      v-if="error"
      class="error small"
      role="alert"
      data-testid="hs-suggest-error"
    >
      {{ error }}
    </p>
    <ul
      v-if="items.length"
      class="contact-list"
      data-testid="hs-suggest-list"
    >
      <li
        v-for="item in items"
        :key="item.hs_code"
      >
        <button
          class="small"
          :data-testid="`hs-pick-${item.hs_code}`"
          @click="pick(item.hs_code)"
        >
          <span class="code">{{ item.hs_code }}</span>
          · {{ item.shipments }} 票
        </button>
        <span class="muted small">{{ item.sample_description }}</span>
      </li>
    </ul>
  </div>
</template>
