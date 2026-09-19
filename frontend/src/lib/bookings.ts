import { useQuery } from "@tanstack/react-query";
import { api, type Booking, type Page } from "./api";

// Creation-date pagination can put a future appointment on a later page.
// Do not show an incomplete calendar as if those dates were empty.
export function useBookings(enabled = true) {
  return useQuery({
    queryKey: ["bookings", "calendar"], enabled,
    queryFn: async ({ signal }) => {
      const items: Booking[] = [];
      let cursor: string | null = null;
      do {
        const page: Page<Booking> = await api(`/me/bookings?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`, { signal });
        items.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor);
      return items.sort((a, b) => a.starts_at.localeCompare(b.starts_at));
    },
  });
}

export const dateKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
export const clockTime = (value: string) => new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
