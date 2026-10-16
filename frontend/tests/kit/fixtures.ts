/** 出海包前端测试共用数据（童装演示）。 */
import type { KitBuyer, KitDraft, KitInquiry, KitProfile, KitTasks } from "@/api/kit";

export const tasks: KitTasks = {
  today: 2,
  done_count: 1,
  total: 3,
  tasks: [
    { key: "d1_buyer_type", day: 1, title: "确定买家类型", page: "today", done: true },
    { key: "d2_pick_products", day: 2, title: "选 3 个主推款", page: "products", done: false },
    { key: "d3_storefront", day: 3, title: "准备 WhatsApp", page: "external", done: false },
  ],
};

export const profile: KitProfile = {
  product_id: 1, code: "Q-1", name: "Organic Baby Romper", has_profile: true,
  image_url: "", specs: "100% cotton", moq: 300, lead_time_days: 30,
  selling_points: ["GOTS"], featured: true,
};

export const buyer: KitBuyer = {
  company_id: 9, name: "Tiny Kids Trading 01 LLC", country: "US", channel: "email",
  stage: "new", contact_id: 77, contact_name: "Buyer 01", email: "b@demo.example.com",
};

export const draft: KitDraft = {
  id: 5, product_id: 1, company_id: 9, company_name: buyer.name, contact_id: 77,
  channel: "email", subject: "Organic Baby Romper for Tiny", body: "Hi Buyer 01",
  source: "template", follow_up_on: ["2026-10-19", "2026-10-23"],
  next_follow_up: "2026-10-19", sent: false,
};

export const inquiry: KitInquiry = {
  id: 3, company_id: 9, company_name: buyer.name, product_id: 1,
  product_name: profile.name, status: "new", status_label: "新询盘", quantity: 600,
  unit_price: "3.25", currency: "USD", total: "1950.00", note: "",
};
