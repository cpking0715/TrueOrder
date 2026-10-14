/** 税号发现：库内反查 + AI 自动推荐。 */

import { requestJson } from "./client";

export interface HsSuggestion {
  hs_code: string;
  shipments: number;
  sample_description: string;
}

export interface AutoHsResult {
  hs_code: string;
  source: string;
  bill_count: number;
}

export function suggestHs(keyword: string): Promise<HsSuggestion[]> {
  return requestJson<HsSuggestion[]>(`/api/hs/suggest?q=${encodeURIComponent(keyword)}`);
}

export function autoHs(name: string): Promise<AutoHsResult> {
  return requestJson<AutoHsResult>("/api/hs/auto", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}
