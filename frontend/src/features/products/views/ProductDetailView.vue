<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import NoticeBanner from "@/components/NoticeBanner.vue";
import { fetchMeta, fetchProducts, type Buyer, type Meta, type Product } from "@/api/products";
import { useBuyerFilters } from "../composables/useBuyerFilters";
import { useBuyerList } from "../composables/useBuyerList";
import { useProductOpportunities } from "../composables/useProductOpportunities";
import ProductHeader from "../components/ProductHeader.vue";
import BuyerTabs from "../components/BuyerTabs.vue";
import FilterBar from "../components/FilterBar.vue";
import BuyerTable from "../components/BuyerTable.vue";
import CompanyDrawer from "../components/CompanyDrawer.vue";
import DetailActions from "../components/DetailActions.vue";
import NoBillsHint from "../components/NoBillsHint.vue";

const route = useRoute();
const productId = computed(() => Number(route.params.id));
const products = ref<Product[]>([]);
const meta = ref<Meta | null>(null);
const audience = ref("importer");
const selectedCompanyId = ref<number | null>(null);

const filters = useBuyerFilters(
  () => productId.value,
  () => audience.value,
);
const buyers = useBuyerList(
  () => productId.value,
  () => audience.value,
  () => filters.state.value,
);
const { result, loading, error } = buyers;
const loadBuyers = buyers.load;
const opps = useProductOpportunities(() => productId.value, selectedCompanyId);
const { followStages, selectedOpportunity } = opps;

async function onFollowUp(buyer: { company_id: number }) {
  const message = await opps.followUp(buyer.company_id);
  if (message) error.value = message;
}

const product = computed(
  () => products.value.find((p) => p.product_id === productId.value) ?? null,
);

// F5：both 产品的页签计数用当前受众的细分数据。
// counts_by_audience 只对有得分行的受众建键：both 某受众缺键 = 该受众无得分（{}），
// 严禁回退总计数，否则空受众页签会串成另一受众的数字（F1 复审）。
const audienceCounts = computed(() => {
  const current = product.value;
  if (!current) return {};
  if (current.buyer_type === "both") {
    return current.counts_by_audience?.[audience.value] ?? {};
  }
  return current.counts_by_audience?.[audience.value] ?? current.counts;
});

// 空结果指引：新产品计数全 0 → 告诉用户去哪补数据
const hasNoBills = computed(() =>
  product.value != null
  && Object.values(audienceCounts.value).reduce((a, b) => a + b, 0) === 0,
);

function followProductAudience() {
  const current = product.value;
  if (current && current.buyer_type !== "both") {
    audience.value = current.buyer_type;
  }
}

function onTierChange() {
  buyers.reset();
  loadBuyers();
}

onMounted(async () => {
  const [metaResult, productsResult] = await Promise.all([
    fetchMeta().catch(() => null),
    fetchProducts(),
  ]);
  void opps.reload();
  meta.value = metaResult;
  products.value = productsResult;
  followProductAudience();
  await loadBuyers();
});

// 同一组件实例在产品间切换（路由复用）时，受众与列表必须跟随新产品
watch(productId, () => {
  followProductAudience();
  buyers.reset();
  void opps.reload();
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
    <NoBillsHint v-if="hasNoBills" />
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
      class="error small"
      role="alert"
    >
      {{ error }}
    </p>
    <BuyerTable
      :buyers="result?.items ?? ([] as Buyer[])"
      :loading="loading"
      :follow-stages="followStages"
      @select="selectedCompanyId = $event.company_id"
      @follow-up="onFollowUp"
    />
    <p
      v-if="result && result.items.length < result.total"
      class="small muted"
      data-testid="truncated-hint"
    >
      已显示前 {{ result.items.length }} 家（共 {{ result.total }} 家），导出 CSV 含全部筛选结果。
    </p>
    <DetailActions
      :product-id="productId"
      :filters="filters.state.value"
      :export-url="filters.exportUrl.value"
    />
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
    :opportunity="selectedOpportunity"
    @close="selectedCompanyId = null"
    @opportunity-changed="opps.reload"
  />
</template>
