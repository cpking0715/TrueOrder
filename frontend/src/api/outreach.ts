/** 开发信域 API：类型来自 OpenAPI 生成。 */

import { requestJson } from "./client";
import type { components } from "./schema";

export type Template = components["schemas"]["TemplateOut"];
export type PreviewResult = components["schemas"]["PreviewOut"];
export type Message = components["schemas"]["MessageOut"];
export type Suppression = components["schemas"]["SuppressionOut"];

export async function fetchTemplates(): Promise<Template[]> {
  return requestJson<Template[]>("/api/outreach/templates");
}

export async function createTemplate(payload: {
  name: string; subject: string; body: string;
}): Promise<Template> {
  return requestJson<Template>("/api/outreach/templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteTemplate(id: number): Promise<void> {
  return requestJson(`/api/outreach/templates/${id}`, { method: "DELETE" });
}

export async function previewEmail(payload: {
  template_id: number; opportunity_id: number; contact_id: number;
}): Promise<PreviewResult> {
  return requestJson<PreviewResult>("/api/outreach/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function queueSend(templateId: number, oppId: number, contactId: number) {
  return requestJson<{ message_id: number; status: string }>("/api/outreach/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preview_token: `${templateId}:${oppId}:${contactId}` }),
  });
}

export async function fetchMessages(status?: string): Promise<Message[]> {
  const q = status ? `?status=${status}` : "";
  return requestJson<Message[]>(`/api/outreach/messages${q}`);
}
