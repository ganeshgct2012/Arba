import { type ConfigTab, type Page } from "./types";

export const pageNames: Record<Page, string> = {
  weekly: "Weekly Volume",
  promotions: "Promotions",
  calendar: "Promo Calendar",
  history: "Sales History",
  report: "Volume Report",
  listing: "Product Listing",
  configuration: "Configuration",
};
export const configNames: Record<ConfigTab, string> = {
  access: "Access Management",
  customer: "Customer Master",
  product: "Product Master",
  batch: "Batch Job Configuration",
  files: "Files",
};
export const roles = ["PLANNER", "APPROVER", "VIEWER"] as const;
export const editableRoles = ["PLANNER", "APPROVER", "ADMIN", "VIEWER"] as const;
export const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
