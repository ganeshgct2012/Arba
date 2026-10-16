import { useEffect, useState } from "react";
import { api } from "../api";
import { Heading } from "../components/Heading";
import { type PageProps } from "../types";
import { errorText } from "../utils";

export function ProductListing(props: PageProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  useEffect(() => {
    api<{ selected: string[] }>(`/listing?market=${props.market}&customer_id=${props.customerId}`)
      .then((result) => setSelected(new Set(result.selected)))
      .catch((error: unknown) => props.setError(errorText(error)));
  }, [props.market, props.customerId, props.refresh, props.setError]);
  async function save() {
    try {
      const result = await api<{ saved: number; delisted_with_plans: string[] }>("/listing", {
        method: "PUT",
        body: JSON.stringify({ market: props.market, customer_id: props.customerId, products: [...selected] }),
      });
      props.flash(`Saved ${result.saved} listed products${result.delisted_with_plans.length ? `. Warning: products with future plans: ${result.delisted_with_plans.join(", ")}` : ""}`);
    } catch (error) { props.setError(errorText(error)); }
  }
  return <><Heading title="Product Listing" subtitle="Choose P09 products available for this plan account" actions={<><button className="button" onClick={() => setSelected(new Set(props.bootstrap.products.map((item) => item.code)))}>Select all</button><button className="button" onClick={() => setSelected(new Set())}>Clear all</button><button className="button primary" onClick={() => void save()}>Save listing</button></>} /><label className="inline-label">Search<input value={filter} onChange={(event) => setFilter(event.target.value)} /></label><div className="product-cards">{props.bootstrap.products.filter((item) => `${item.code} ${item.description} ${item.brand}`.toLowerCase().includes(filter.toLowerCase())).map((item) => <label className="product-choice" key={item.code}><input checked={selected.has(item.code)} type="checkbox" onChange={(event) => setSelected((current) => { const next = new Set(current); if (event.target.checked) next.add(item.code); else next.delete(item.code); return next; })} /><span><b>{item.description}</b><small>{item.brand} · {item.sub_brand} · {item.code}</small></span></label>)}</div></>;
}

