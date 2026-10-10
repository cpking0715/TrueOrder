/** 联系人域 API（WP1）：类型来自 OpenAPI 生成，不手写接口类型。 */

import { ApiError, requestJson, uploadJson } from "./client";
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
  // 204 无响应体，不能走 requestJson 的 json 解析
  const response = await fetch(`/api/contacts/${contactId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }
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
  return `/api/products/${productId}/contacts/export.csv?${search}`;
}
