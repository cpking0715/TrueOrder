<script setup lang="ts">
import { ref } from "vue";
import { uploadBillsCsv, uploadProductsCsv, type ImportSummary } from "@/api/products";
import { useRouter } from "vue-router";

const emit = defineEmits<{ imported: [] }>();
const router = useRouter();
const message = ref("");
const busy = ref(false);

function describe(summary: ImportSummary): string {
  const parts: string[] = [];
  if (summary.products_upserted) parts.push(`产品 ${summary.products_upserted} 个`);
  if (summary.inserted_bills) parts.push(`新增提单 ${summary.inserted_bills} 票`);
  if (summary.duplicate_bills) parts.push(`重复跳过 ${summary.duplicate_bills} 票`);
  if (summary.suspect_hs_bills) parts.push(`税号可疑 ${summary.suspect_hs_bills} 票`);
  if (summary.companies_created) parts.push(`新建企业 ${summary.companies_created} 家`);
  if (summary.invalid_rows?.length) parts.push(`非法行 ${summary.invalid_rows.length} 行`);
  const rescored = summary.rescore?.map((r) => `${r.product_code}: 精准${r.precise}`).join("；");
  return `导入完成：${parts.join("，") || "无变化"}${rescored ? `；${rescored}` : ""}`;
}

async function onProductsFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  busy.value = true;
  try {
    message.value = describe(await uploadProductsCsv(file));
    emit("imported");
  } catch (error) {
    message.value = `导入失败：${(error as Error).message}`;
  } finally {
    busy.value = false;
    (event.target as HTMLInputElement).value = "";
  }
}

async function onBillsFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  busy.value = true;
  try {
    message.value = describe(await uploadBillsCsv(file));
    emit("imported");
    router.go(0);
  } catch (error) {
    message.value = `导入失败：${(error as Error).message}`;
  } finally {
    busy.value = false;
    (event.target as HTMLInputElement).value = "";
  }
}
</script>

<template>
  <div
    class="panel"
    data-testid="import-panel"
  >
    <h2>数据导入（CSV）</h2>
    <p class="muted small">
      产品目录每行一个产品 + 税号 + 买家类型；提单走同一入口，导入后自动重新打分。
      样本字段说明见 backend/app/seed/sample_bills.README.md。
    </p>
    <label class="btn">
      导入产品 CSV
      <input
        type="file"
        accept=".csv"
        hidden
        data-testid="products-file"
        @change="onProductsFile"
      >
    </label>
    <label
      class="btn"
      style="margin-left: 8px"
    >
      导入提单 CSV
      <input
        type="file"
        accept=".csv"
        hidden
        data-testid="bills-file"
        @change="onBillsFile"
      >
    </label>
    <span
      v-if="busy"
      class="muted"
      style="margin-left: 10px"
    >处理中…</span>
    <p
      v-if="message"
      data-testid="import-message"
      class="small"
    >
      {{ message }}
    </p>
  </div>
</template>
