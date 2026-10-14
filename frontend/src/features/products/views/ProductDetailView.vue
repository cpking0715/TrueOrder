<script setup lang="ts">
import { withApiToken } from "@/api/client";
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
import {
  createOpportunity,
  fetchOpportunities,
  type Opportunity,
} from "@/api/opportunities";
import { useBuyerFilters } from "../composables/useBuyerFilters";
import ProductHeader from "../components/ProductHeader.vue";
import BuyerTabs from "../components/BuyerTabs.vue";
import FilterBar from "../components/FilterBar.vue";
import BuyerTable from "../components/BuyerTable.vue";
import CompanyDrawer from "../components/CompanyDrawer.vue";
import EnrichBar from "../components/EnrichBar.vue";

const route = useRoute();
const productId = computed(() => Number(route.params.id));
const products = ref<Product[]>([]);
const meta = ref<Meta | null>(null);
const audience = ref("importer");
const result = ref<BuyerList | null>(null);
const loading = ref(false);
const selectedCompanyId = ref<number | null>(null);

// 联系人导出与买家导出共用同一筛选参数：取 buyers 导出 URL 的查询串换成 contacts 路径
const contactsExportUrl = computed(() => {
  const url = filters.exportUrl.value;
  const search = url.includes("?") ? url.slice(url.indexOf("?")) : "";
  return withApiToken(`/api/products/${route.params.id}/contacts/export.csv${search}`);
});
const error = ref("");
const opportunities = ref<Opportunity[]>([]);

const followStages = computed(() =>
  Object.fromEntries(opportunities.value.map((o) => [o.company_id, o.stage])),
);
const selectedOpportunity = computed(
  () => opportunities.value.find((o) => o.company_id === selectedCompanyId.value) ?? null,
);

async function reloadOpportunities() {
  try {
    opportunities.value = await fetchOpportunities({ product_id: productId.value });
  } catch {
    opportunities.value = [];
  }
}

async function onFollowUp(buyer: { company_id: number }) {
  try {
    await createOpportunity(productId.value, buyer.company_id);
    await reloadOpportunities();
  } catch (e) {
    error.value = `加入跟进失败：${(e as Error).message}`;
  }
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
  void reloadOpportunities();
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
  void reloadOpportunities();
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
    <p
      v-if="hasNoBills"
      class="alert"
      data-testid="no-bills-hint"
    >
      库里还没有该税号的提单。两条路：到
      <RouterLink to="/">
        首页底部的「导入提单 CSV」
      </RouterLink>
      导入授权数据；或没有提单时直接点上方「AI 买家发现」，让 AI 从品名捞市场客户。
    </p>
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
    <div class="detail-actions">
      <EnrichBar
        :product-id="productId"
        :query="{
          tier: filters.state.value.tier,
          q: filters.state.value.q,
          country: filters.state.value.country,
          minShipments: filters.state.value.minShipments,
        }"
      />
      <span class="actions">
        <a
          class="btn primary"
          :href="filters.exportUrl.value"
          download
          data-testid="export-button"
          title="导出当前筛选的全部结果（不受列表显示条数限制）"
        >
          导出买家 CSV
        </a>
        <a
          class="btn"
          :href="contactsExportUrl"
          download
          data-testid="export-contacts-button"
          title="按当前筛选导出联系人（默认排除不再联系与无效邮箱）"
        >
          导出联系人 CSV
        </a>
      </span>
    </div>
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
    @opportunity-changed="reloadOpportunities"
  />
</template>
