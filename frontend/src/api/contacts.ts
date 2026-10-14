/** 联系人域 API（WP1）：类型来自 OpenAPI 生成，不手写接口类型。 */

import { requestJson, uploadJson, withApiToken } from "./client";
import { buildBuyersParams, type BuyerQuery } from "./products";
import type { components } from "./schema";

export type Contact = components["schemas"]["ContactOut"];
export type ContactCreate = components["schemas"]["ContactCreateIn"];
export type ContactUpdate = components["schemas"]["ContactUpdateIn"];
export type CompanyWebsite = components["schemas"]["CompanyWebsiteOut"];
export type ContactsImportSummary = components["schemas"]["ContactsImportOut"];

export async function fetchContacts(companyId: number): Promise<Contact[]> {
  return requestJson<Contact[]>(`/api/companies/${companyId}/contacts`);
}

export async function createContact(companyId: number, payload: ContactCreate): Promise<Contact> {
  return requestJson<Contact>(`/api/companies/${companyId}/contacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateContact(contactId: number, payload: ContactUpdate): Promise<Contact> {
  return requestJson<Contact>(`/api/contacts/${contactId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteContact(contactId: number): Promise<void> {
  await requestJson<void>(`/api/contacts/${contactId}`, { method: "DELETE" });
}

export async function patchCompanyWebsite(
  companyId: number,
  payload: { website?: string; website_confirmed?: boolean },
): Promise<CompanyWebsite> {
  return requestJson<CompanyWebsite>(`/api/companies/${companyId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function uploadContactsCsv(file: File): Promise<ContactsImportSummary> {
  return uploadJson<ContactsImportSummary>("/api/contacts/import", file);
}

// 与买家列表同一组筛选导出联系人（默认排除不再联系与无效邮箱）
export function contactsExportUrl(productId: number, query: BuyerQuery): string {
  const search = new URLSearchParams(buildBuyersParams(query)).toString();
  return withApiToken(`/api/products/${productId}/contacts/export.csv?${search}`);
}

// ---------- WP4 补全与抓取 ----------

// 估计与执行共用响应形状（EnrichExecutedOut 含估计全部字段，confirm=false 时 enqueued=0）
export type EnrichEstimate = components["schemas"]["EnrichExecutedOut"];

export interface EnrichRequest {
  tier?: string;
  q?: string;
  country?: string;
  min_shipments?: number;
  limit: number;
  confirm: boolean;
}

/** 对单个选定企业触发补全（finder=按域名/公司名，website=抓官网公开页） */
export async function requestFindContacts(
  companyId: number,
  method: "finder" | "website" = "finder",
): Promise<{ job_id: number; kind: string }> {
  return requestJson(`/api/companies/${companyId}/find-contacts?method=${method}`, {
    method: "POST",
  });
}

/** 把中低置信的域名候选确认为官网 */
export async function confirmWebsite(companyId: number): Promise<CompanyWebsite> {
  return requestJson<CompanyWebsite>(`/api/companies/${companyId}/website/confirm`, {
    method: "POST",
  });
}

/** 批量补全：不带 confirm 只拿估计；confirm=true 入队执行 */
export async function enrichBuyers(
  productId: number,
  payload: EnrichRequest,
): Promise<EnrichEstimate & { enqueued?: number; job_ids?: number[] }> {
  return requestJson(`/api/products/${productId}/buyers/enrich`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export interface EnrichUsage {
  provider: string;
  configured: boolean;
  daily_cap: number;
  used_today: number;
  remaining: number;
}

export async function fetchEnrichUsage(): Promise<EnrichUsage> {
  return requestJson<EnrichUsage>("/api/enrichment/usage");
}
