import { useEffect, useState } from "react";
import { api } from "../api";
import { Heading } from "../components/Heading";
import { type PageProps } from "../types";
import { errorText } from "../utils";

export function VolumeReport(props: PageProps) {
  const [year, setYear] = useState(new Date().getFullYear());
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [months, setMonths] = useState<string[]>([]);
  useEffect(() => {
    api<{ rows: Record<string, unknown>[]; month_names: string[] }>(`/report?market=${props.market}&year=${year}&customer_id=${props.customerId}`)
      .then((result) => { setRows(result.rows); setMonths(result.month_names); })
      .catch((error: unknown) => props.setError(errorText(error)));
  }, [props.market, props.customerId, props.refresh, props.setError, year]);
  const filtered = rows.filter((row) => props.products.some((product) => product.code === row.product));
  return <><Heading title="Volume Report" subtitle={`${props.market} · weekly volumes assigned to the month of the ISO-week Thursday`} actions={<label className="compact-label">Year<select value={year} onChange={(event) => setYear(Number(event.target.value))}>{[year - 1, year, year + 1].map((value) => <option key={value}>{value}</option>)}</select></label>} /><div className="table-scroll"><table className="data-table"><thead><tr><th>Plan Account</th><th>Product</th>{months.map((month) => <th key={month}>{month}</th>)}<th>Total</th></tr></thead><tbody>{filtered.map((row, index) => { const monthly = row.months as number[]; return <tr key={`${String(row.customer_id)}-${String(row.product)}-${index}`}><td>{String(row.customer)}</td><td>{String(row.description)}</td>{monthly.map((value, month) => <td key={month}>{value}</td>)}<td><b>{String(row.total)}</b></td></tr>; })}</tbody></table></div></>;
}

