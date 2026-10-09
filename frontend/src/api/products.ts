/** 产品域 API：类型来自后端 OpenAPI 生成（pnpm gen:api），不手写接口类型。 */

import { requestJson, uploadJson } from "./client";
import type { components } from "./schema";

export type Meta = components["schemas"]["MetaOut"];
export type Product = components["schemas"]["ProductOut"];
export type Buyer = components["schemas"]["BuyerOut"];
export type BuyerList = components["schemas"]["BuyerListOut"];
export type CompanyDetail = components["schemas"]["CompanyDetailOut"];
export type ImportSummary = components["schemas"]["ImportSummaryOut"];

export type Tier = "potential" | "precise" | "excluded";
export type Order = "shipments" | "last_arrival" | "name";

export interface BuyerQuery {
  audience?: string;
  tier?: Tier;
  q?: string;
  country?: string;
  minShipments?: number;
  order?: Order;
  limit?: number;
}

export async function fetchMeta(): Promise<Meta> {
  return requestJson<Meta>("/api/meta");
}

export async function fetchProducts(): Promise<Product[]> {
  return requestJson<Product[]>("/api/products");
}

export function buildBuyersParams(query: BuyerQuery): Record<string, string> {
  const params: Record<string, string> = {};
  if (query.audience) params.audience = query.audience;
  if (query.tier) params.tier = query.tier;
  if (query.q?.trim()) params.q = query.q.trim();
  if (query.country?.trim()) params.country = query.country.trim().toUpperCase();
  if (query.minShipments && query.minShipments > 1) params.min_shipments = String(query.minShipments);
  if (query.order) params.order = query.order;
  if (query.limit) params.limit = String(query.limit);
  return params;
}

export async function fetchBuyers(productId: number, query: BuyerQuery): Promise<BuyerList> {
  const search = new URLSearchParams(buildBuyersParams(query)).toString();
  return requestJson<BuyerList>(`/api/products/${productId}/buyers?${search}`);
}

// 列表与导出共用同一筛选参数构造；导出返回全部筛选结果（列表可能截断）
export const BUYERS_PAGE_LIMIT = 500;

export function buyersExportUrl(productId: number, query: BuyerQuery): string {
  const search = new URLSearchParams(buildBuyersParams(query)).toString();
  return `/api/products/${productId}/buyers/export.csv?${search}`;
}

export async function fetchCompany(
  companyId: number,
  productId?: number,
  audience?: string,
): Promise<CompanyDetail> {
  const params = new URLSearchParams();
  if (productId) params.set("product_id", String(productId));
  if (audience) params.set("audience", audience);
  const search = params.size ? `?${params.toString()}` : "";
  return requestJson<CompanyDetail>(`/api/companies/${companyId}${search}`);
}

export async function uploadProductsCsv(file: File): Promise<ImportSummary> {
  return uploadJson<ImportSummary>("/api/products/import", file);
}

export async function uploadBillsCsv(file: File, asOf?: string): Promise<ImportSummary> {
  return uploadJson<ImportSummary>("/api/bills/import", file, asOf ? { as_of: asOf } : undefined);
}
