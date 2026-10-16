import { useEffect, useState } from "react";
import { api } from "../api";
import { Heading } from "../components/Heading";
import { type CalendarPromotion, type PageProps } from "../types";
import { errorText, isoWeekForDate } from "../utils";

export function PromoCalendar(props: PageProps) {
  const [items, setItems] = useState<CalendarPromotion[]>([]);
  const [weeks, setWeeks] = useState<string[]>([]);
  useEffect(() => {
    api<{ weeks: string[]; promotions: CalendarPromotion[] }>(`/calendar?market=${props.market}&customer_id=${props.customerId}`)
      .then((result) => { setItems(result.promotions); setWeeks(result.weeks); })
      .catch((error: unknown) => props.setError(errorText(error)));
  }, [props.market, props.customerId, props.refresh, props.setError]);
  const statusLabels: Record<string, string> = { SAVED: "Planned", CHANGED: "Approval Pending", APPROVED: "Approved" };
  return <><Heading title="Promo Calendar" subtitle={`${props.market} · ${items.length} promotion and sub-brand rows`} />
    <div className="calendar-legend"><span className="calendar-status planned">Planned</span><span className="calendar-status approval-pending">Approval Pending</span><span className="calendar-status approved">Approved</span></div>
    <div className="table-scroll"><table className="data-table wide-table promo-calendar-table"><thead><tr><th>Promotion</th><th>Customer</th><th>Sub-brand</th><th>Products</th>{weeks.map((week) => <th key={week}>{week}</th>)}</tr></thead><tbody>{items.map((item, index) => {
      const firstWeek = isoWeekForDate(item.start_date);
      const lastWeek = isoWeekForDate(item.end_date);
      return <tr key={`${item.id}-${item.sub_brand}-${index}`}>
        <td><button className="text-button" onClick={() => props.onOpenPromotion(item.id)}>{item.promo_number}</button></td><td>{item.customer_name}</td><td>{item.sub_brand}</td><td>{item.product_count}</td>
        {weeks.map((week) => <td className={week >= firstWeek && week <= lastWeek ? `calendar-week ${item.status === "APPROVED" ? "approved" : item.status === "CHANGED" ? "approval-pending" : "planned"}` : ""} key={week}>{week >= firstWeek && week <= lastWeek ? <span title={`${statusLabels[item.status]} · ${item.tactic}`}>{item.tactic}</span> : null}</td>)}
      </tr>;
    })}
      {!items.length && <tr><td className="empty-cell" colSpan={weeks.length + 4}>No Planned, Approval Pending, or Approved promotions for this plan account.</td></tr>}
    </tbody></table></div>
  </>;
}

