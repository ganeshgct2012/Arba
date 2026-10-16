import { type User } from "./api";

export type Market = {
  code: string;
  name: string;
  plan_mode: "VOL" | "PROMO";
  p10_sales_org: string;
  horizon_weeks: number;
};
export type Customer = { id: number; market_code: string; name: string };
export type Product = {
  code: string;
  description: string;
  brand: string;
  sub_brand: string;
  category: string;
};
export type Tactic = { market_code: string; name: string };
export type Bootstrap = {
  markets: Market[];
  customers: Customer[];
  products: Product[];
  tactics: Tactic[];
  listings: { market_code: string; customer_id: number; p09_code: string }[];
  weeks: string[];
  history_weeks: string[];
};
export type BaselineProduct = Product & { baseline: number[]; actual_last_year: number[] };
export type BaselineData = { weeks: string[]; products: BaselineProduct[] };
export type PromotionItem = {
  product: string;
  description: string;
  baseline: number;
  total: number;
  uplift: number;
  actual: number;
};
export type Promotion = {
  id: number;
  version: number;
  promo_number: string;
  market_code: string;
  customer_id: number;
  customer_name: string;
  start_date: string;
  end_date: string;
  cons_start: string;
  cons_end: string;
  tactic: string;
  status: string;
  baseline: number;
  total: number;
  uplift: number;
  actual: number;
  items: PromotionItem[];
};
export type CalendarPromotion = {
  id: number;
  promo_number: string;
  start_date: string;
  end_date: string;
  tactic: string;
  status: string;
  customer_name: string;
  sub_brand: string;
  product_count: number;
};
export type AccountAssignment = { market_code: string; customer_id: number };
export type AdminUser = User & {
  active: boolean;
  last_login_at: string | null;
  sales_org_access: string[];
  admin_sales_org_access: string[];
};
export type SalesOrg = { code: string; name: string };
export type AccessData = {
  users: AdminUser[];
  assignments: (AccountAssignment & {
    user_id: number;
    customer_name: string;
  })[];
  sales_orgs: SalesOrg[];
};
export type Pipeline = {
  id: string;
  name: string;
  direction: string;
  source: string;
  target: string;
  connector_type: string;
  config_json: { file_path?: string | null; [key: string]: unknown };
  enabled: boolean;
  schedule_frequency: "DAILY" | "WEEKLY" | "MONTHLY" | "QUARTERLY";
  schedule_timezone: string;
  schedule_time: string;
  schedule_weekday: number;
  schedule_month_day: number;
  schedule_quarter_month: number;
  schedule_start_date: string | null;
  schedule_end_date: string | null;
  next_run_at: string | null;
  last_run: null | { status: string; finished_at: string | null; started_at: string | null };
};
export type ManagedFile = {
  id: number;
  direction: "INBOUND" | "OUTBOUND";
  category: string;
  original_name: string;
  status: string;
  uploaded_by: string;
  created_at: string;
  processed_at: string | null;
  row_count: number;
  message: string | null;
};
export type Page =
  | "weekly"
  | "promotions"
  | "calendar"
  | "history"
  | "report"
  | "listing"
  | "configuration";
export type ConfigTab = "access" | "customer" | "product" | "batch" | "files";

export type PageProps = {
  page: Page;
  market: string;
  customerId: number;
  user: User;
  bootstrap: Bootstrap;
  products: Product[];
  flash: (message: string) => void;
  setError: (message: string) => void;
  refresh: () => void;
  openPromotionId: number | null;
  onPromotionOpened: () => void;
  onOpenPromotion: (promotionId: number) => void;
};
