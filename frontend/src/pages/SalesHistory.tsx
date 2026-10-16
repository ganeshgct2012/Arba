import { useEffect, useState } from "react";
import { api } from "../api";
import { Heading } from "../components/Heading";
import { type PageProps, type Product } from "../types";
import { errorText } from "../utils";

export function SalesHistory(props: PageProps) {
  const [data, setData] = useState<{ weeks: string[]; products: (Product & { values: number[] })[] } | null>(null);
  useEffect(() => {
    api<{ weeks: string[]; products: (Product & { values: number[] })[] }>(`/history?market=${props.market}&customer_id=${props.customerId}`)
      .then(setData).catch((error: unknown) => props.setError(errorText(error)));
  }, [props.market, props.customerId, props.refresh, props.setError]);
  if (!data) return <p className="muted">Loading sales history…</p>;
  return <><Heading title="Sales History" subtitle={`${props.market} · actual sell-in · cases (CS)`} /><div className="table-scroll"><table className="data-table wide-table"><thead><tr><th>Product</th>{data.weeks.map((week) => <th key={week}>{week}</th>)}</tr></thead><tbody>{data.products.filter((item) => props.products.some((product) => product.code === item.code)).map((item) => <tr key={item.code}><td className="sticky-product">{item.description}<small>{item.code}</small></td>{item.values.map((value, index) => <td key={data.weeks[index]}>{value}</td>)}</tr>)}</tbody></table></div></>;
}

