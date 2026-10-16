/** 出海包 v0.1（内部工具）API：类型来自 OpenAPI 生成。只生成草稿，不提供任何发送接口。 */

import { requestJson, uploadJson, withApiToken } from "./client";
import type { components } from "./schema";

export type KitTasks = components["schemas"]["KitTasksOut"];
export type KitTask = components["schemas"]["KitTaskOut"];
export type KitProfile = components["schemas"]["KitProfileOut"];
export type KitProfileIn = components["schemas"]["KitProfileIn"];
export type KitBuyer = components["schemas"]["KitBuyerOut"];
export type KitBuyerImport = components["schemas"]["KitBuyerImportOut"];
export type KitDraft = components["schemas"]["KitDraftOut"];
export type KitDraftIn = components["schemas"]["KitDraftIn"];
export type KitInquiry = components["schemas"]["KitInquiryOut"];
export type KitInquiryIn = components["schemas"]["KitInquiryIn"];
export type InquiryStatus = components["schemas"]["KitInquiryPatchIn"]["status"];

const JSON_HEADERS = { "Content-Type": "application/json" };

function send<T>(url: string, method: string, body: unknown): Promise<T> {
  return requestJson<T>(url, { method, headers: JSON_HEADERS, body: JSON.stringify(body) });
}

export const fetchKitTasks = () => requestJson<KitTasks>("/api/kit/tasks");
export const setKitTaskDone = (key: string, done: boolean) =>
  send<void>(`/api/kit/tasks/${key}`, "PUT", { done });

export const fetchKitProfiles = () => requestJson<KitProfile[]>("/api/kit/products");
export const saveKitProfile = (productId: number, payload: KitProfileIn) =>
  send<KitProfile>(`/api/kit/products/${productId}/profile`, "PUT", payload);

export const importKitBuyers = (file: File) =>
  uploadJson<KitBuyerImport>("/api/kit/buyers/import", file);
export function fetchKitBuyers(filters: { country?: string; channel?: string; stage?: string } = {}) {
  const q = new URLSearchParams(Object.entries(filters).filter(([, v]) => v) as string[][]);
  const qs = q.toString();
  return requestJson<KitBuyer[]>(`/api/kit/buyers${qs ? `?${qs}` : ""}`);
}
export const patchKitBuyer = (companyId: number, payload: { channel?: string; stage?: string }) =>
  send<void>(`/api/kit/buyers/${companyId}`, "PATCH", payload);

export const createKitDraft = (payload: KitDraftIn) => send<KitDraft>("/api/kit/drafts", "POST", payload);
export const fetchKitDrafts = () => requestJson<KitDraft[]>("/api/kit/drafts");
export const draftExportUrl = (id: number) => withApiToken(`/api/kit/drafts/${id}/export.txt`);

export const fetchKitInquiries = () => requestJson<KitInquiry[]>("/api/kit/inquiries");
export const createKitInquiry = (payload: KitInquiryIn) =>
  send<KitInquiry>("/api/kit/inquiries", "POST", payload);
export const setInquiryStatus = (id: number, status: InquiryStatus) =>
  send<KitInquiry>(`/api/kit/inquiries/${id}`, "PATCH", { status });
export const piPdfUrl = (id: number) => withApiToken(`/api/kit/inquiries/${id}/pi.pdf`);
