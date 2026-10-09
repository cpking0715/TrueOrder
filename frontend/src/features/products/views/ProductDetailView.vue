<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import NoticeBanner from "@/components/NoticeBanner.vue";
import {
  BUYERS_PAGE_LIMIT,
  fetchBuyers,
  fetchMeta,
  fetchProducts,
  type Buyer,
  type BuyerList,
  type Meta,
  type Product,
} from "@/api/products";
import { useBuyerFilters } from "../composables/useBuyerFilters";
import ProductHeader from "../components/ProductHeader.vue";
import BuyerTabs from "../components/BuyerTabs.vue";
import FilterBar from "../components/FilterBar.vue";
import BuyerTable from "../components/BuyerTable.vue";
import CompanyDrawer from "../components/CompanyDrawer.vue";

const route = useRoute();
const productId = computed(() => Number(route.params.id));
const products = ref<Product[]>([]);
const meta = ref<Meta | null>(null);
const audience = ref("importer");
const result = ref<BuyerList | null>(null);
const loading = ref(false);
const selectedCompanyId = ref<number | null>(null);
const error = ref("");

const product = computed(
  () => products.value.find((p) => p.product_id === productId.value) ?? null,
);

// F5：both 产品的页签计数用当前受众的细分数据；单受众产品退回总计数
const audienceCounts = computed(() => {
  const current = product.value;
  if (!current) return {};
  return current.counts_by_audience?.[audience.value] ?? current.counts;
});

const filters = useBuyerFilters(
  () => productId.value,
  () => audience.value,
);

// 逐字符搜索会并发多个请求；过期响应不允许覆盖新响应
let requestSeq = 0;

async function loadBuyers() {
  const seq = ++requestSeq;
  loading.value = true;
  error.value = "";
  try {
    const data = await fetchBuyers(productId.value, {
      audience: audience.value,
      tier: filters.state.value.tier,
      q: filters.state.value.q,
      country: filters.state.value.country,
      minShipments: filters.state.value.minShipments,
      order: filters.state.value.order,
      limit: BUYERS_PAGE_LIMIT,
    });
    if (seq !== requestSeq) return;
    result.value = data;
  } catch (e) {
    if (seq !== requestSeq) return;
    error.value = `加载买家失败：${(e as Error).message}`;
  } finally {
    if (seq === requestSeq) {
      loading.value = false;
    }
  }
}

function onTierChange() {
  result.value = null;
  loadBuyers();
}

onMounted(async () => {
  const [metaResult, productsResult] = await Promise.all([
    fetchMeta().catch(() => null),
    fetchProducts(),
  ]);
  meta.value = metaResult;
  products.value = productsResult;
  const current = product.value;
  if (current && current.buyer_type !== "both") {
    audience.value = current.buyer_type;
  }
  await loadBuyers();
});

// 同一组件实例在产品间切换（路由复用）时，受众与列表必须跟随新产品
watch(productId, () => {
  const current = product.value;
  if (current && current.buyer_type !== "both") {
    audience.value = current.buyer_type;
  }
  result.value = null;
  loadBuyers();
});

watch(
  () => filters.params.value,
  () => loadBuyers(),
);
</script>

<template>
  <RouterLink
    to="/"
    class="backlink"
  >
    ← 返回产品列表
  </RouterLink>
  <NoticeBanner
    v-if="meta?.sample_mode"
    :notice="meta.sample_notice"
  />
  <div
    v-if="product"
    class="panel"
  >
    <ProductHeader
      :product="product"
      :audience="audience"
      @update:audience="audience = $event; loadBuyers()"
    />
    <BuyerTabs
      :tier="filters.state.value.tier"
      :counts="audienceCounts"
      @change="filters.state.value.tier = $event; onTierChange()"
    />
    <FilterBar
      :state="filters.state.value"
      :total="result?.total ?? 0"
      @update:q="filters.state.value.q = $event"
      @update:country="filters.state.value.country = $event"
      @update:min-shipments="filters.state.value.minShipments = $event"
      @update:order="filters.state.value.order = $event"
      @changed="loadBuyers"
    />
    <p
      v-if="error"
      class="badge excluded"
    >
      {{ error }}
    </p>
    <BuyerTable
      :buyers="result?.items ?? ([] as Buyer[])"
      :loading="loading"
      @select="selectedCompanyId = $event.company_id"
    />
    <p
      v-if="result && result.items.length < result.total"
      class="small muted"
      data-testid="truncated-hint"
    >
      已显示前 {{ result.items.length }} 家（共 {{ result.total }} 家），导出 CSV 含全部筛选结果。
    </p>
    <p style="margin-top: 12px">
      <a
        class="btn primary"
        :href="filters.exportUrl.value"
        download
        data-testid="export-button"
        title="导出当前筛选的全部结果（不受列表显示条数限制）"
      >
        导出当前筛选 CSV（全部）
      </a>
    </p>
  </div>
  <div
    v-else
    class="panel empty"
  >
    产品不存在或仍在加载。
  </div>
  <CompanyDrawer
    :company-id="selectedCompanyId"
    :product-id="productId"
    :audience="audience"
    @close="selectedCompanyId = null"
  />
</template>
