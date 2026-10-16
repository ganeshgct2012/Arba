import { type AccountAssignment } from "./types";

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected error. Please try again.";
}

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function assignmentKey(assignment: AccountAssignment): string {
  return `${assignment.market_code}|${assignment.customer_id}`;
}

export function accountValues(select: HTMLSelectElement): AccountAssignment[] {
  return Array.from(select.selectedOptions, (option) => {
    const [market_code, id] = option.value.split("|");
    return { market_code, customer_id: Number(id) };
  });
}

export function multiValues(select: HTMLSelectElement): string[] {
  return Array.from(select.selectedOptions, (option) => option.value);
}

export async function encodeFile(file: File): Promise<string> {
  if (file.size > 10_000_000) throw new Error("The file must be no larger than 10 MB.");
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 32_768) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 32_768));
  }
  return btoa(binary);
}

export async function downloadApiFile(path: string, fallbackName: string): Promise<void> {
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? "/api/v1"}${path}`, {
    credentials: "include",
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the HTTP error when the response isn't JSON.
    }
    throw new Error(message);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition");
  const filename = disposition?.match(/filename="([^"]+)"/i)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}


export function isoWeekForDate(value: string): string {
  const day = new Date(`${value}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + 4 - (day.getUTCDay() || 7));
  const year = day.getUTCFullYear();
  const firstThursday = new Date(Date.UTC(year, 0, 4));
  firstThursday.setUTCDate(firstThursday.getUTCDate() + 4 - (firstThursday.getUTCDay() || 7));
  const week = 1 + Math.round((day.getTime() - firstThursday.getTime()) / 604_800_000);
  return `${year}-W${String(week).padStart(2, "0")}`;
}

