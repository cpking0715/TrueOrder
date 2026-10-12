/** 商机域 API（WP2）：类型来自 OpenAPI 生成，组件不直接 fetch。 */

import { requestJson } from "./client";
import type { components } from "./schema";

export type Opportunity = components["schemas"]["OpportunityOut"];
export type Activity = components["schemas"]["ActivityOut"];
export type Stage =
  | "lead" | "contacted" | "replied" | "sample_quote" | "negotiating" | "won_intent" | "lost";

export const STAGE_LABEL: Record<Stage, string> = {
  lead: "线索",
  contacted: "已联系",
  replied: "已回复",
  sample_quote: "样品/报价",
  negotiating: "谈判中",
  won_intent: "成交意向",
  lost: "已流失",
};

export async function fetchOpportunities(params?: {
  product_id?: number; stage?: string; due?: "today";
}): Promise<Opportunity[]> {
  const search = new URLSearchParams(
    Object.entries(params ?? {}).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
  ).toString();
  return requestJson<Opportunity[]>(`/api/opportunities${search ? `?${search}` : ""}`);
}

export async function createOpportunity(productId: number, companyId: number): Promise<Opportunity> {
  return requestJson<Opportunity>("/api/opportunities", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id: productId, company_id: companyId }),
  });
}

export async function patchOpportunity(
  id: number,
  payload: Partial<{ stage: Stage; closed_reason: string; intent: string;
    next_follow_up_on: string; owner_note: string }>,
): Promise<Opportunity> {
  return requestJson<Opportunity>(`/api/opportunities/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function addActivity(
  id: number,
  payload: { kind: string; summary: string; body?: string; intent_after?: string },
): Promise<Activity> {
  return requestJson<Activity>(`/api/opportunities/${id}/activities`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function fetchTimeline(id: number): Promise<Activity[]> {
  return requestJson<Activity[]>(`/api/opportunities/${id}/timeline`);
}
