import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { Heading } from "../components/Heading";
import { type PageProps, type Promotion } from "../types";
import { errorText, today } from "../utils";

export function Promotions(props: PageProps) {
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<Promotion | null>(null);
  const [selectedProducts, setSelectedProducts] = useState<string[]>([]);
  const [productToAdd, setProductToAdd] = useState("");
  const [totals, setTotals] = useState<Record<string, number>>({});
  const [baselines, setBaselines] = useState<Record<string, number> | null>(null);
  const previousBaselines = useRef<Record<string, number> | null>(null);
  const [start, setStart] = useState(today());
  const [end, setEnd] = useState(today());
  const [consStart, setConsStart] = useState(today());
  const [consEnd, setConsEnd] = useState(today());
  const [tactic, setTactic] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const reload = useCallback(() => {
    api<{ promotions: Promotion[] }>(`/promotions?market=${props.market}&customer_id=${props.customerId}`)
      .then((result) => setPromotions(result.promotions))
      .catch((error: unknown) => props.setError(errorText(error)));
  }, [props.market, props.customerId, props.setError]);
  useEffect(reload, [reload, props.refresh]);
  useEffect(() => {
    setBaselines(null);
    let currentRequest = true;
    api<{ baselines: Record<string, number> }>(
      `/promotions/baseline?market=${props.market}&customer_id=${props.customerId}&start_date=${start}&end_date=${end}`,
    )
      .then((result) => { if (currentRequest) setBaselines(result.baselines); })
      .catch((error: unknown) => { if (currentRequest) props.setError(errorText(error)); });
    return () => { currentRequest = false; };
  }, [props.market, props.customerId, props.setError, start, end]);
  const listed = props.bootstrap.listings.filter((item) => item.market_code === props.market && item.customer_id === props.customerId).map((item) => item.p09_code);
  const available = props.bootstrap.products.filter((item) => listed.includes(item.code));
  const tactics = props.bootstrap.tactics.filter((item) => item.market_code === props.market);
  function baselineFor(code: string): number {
    return baselines?.[code] ?? 0;
  }
  useEffect(() => {
    if (baselines === null) return;
    const previous = previousBaselines.current;
    setTotals((current) => {
      const next = { ...current };
      for (const code of selectedProducts) {
        const baseline = baselineFor(code);
        if (next[code] === undefined) next[code] = baseline;
        else if (previous?.[code] !== undefined) {
          next[code] = baseline + Math.max(0, next[code] - previous[code]);
        }
      }
      return next;
    });
    previousBaselines.current = baselines;
  }, [selectedProducts, baselines]);
  useEffect(() => {
    if (props.openPromotionId === null || !promotions.some((promo) => promo.id === props.openPromotionId)) return;
    const promotionId = props.openPromotionId;
    setExpanded((current) => new Set(current).add(promotionId));
    window.requestAnimationFrame(() => {
      document.getElementById(`promotion-${promotionId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
    props.onPromotionOpened();
  }, [props.openPromotionId, props.onPromotionOpened, promotions]);
  function startCreate() {
    setEditing(null);
    setSelectedProducts([]);
    setProductToAdd("");
    setTotals({});
    previousBaselines.current = null;
    setStart(today());
    setEnd(today());
    setConsStart(today());
    setConsEnd(today());
    setTactic("");
    setShowCreate(true);
  }
  function startEdit(promo: Promotion) {
    setEditing(promo);
    setSelectedProducts(promo.items.map((item) => item.product));
    setProductToAdd("");
    setTotals(Object.fromEntries(promo.items.map((item) => [item.product, item.total])));
    previousBaselines.current = Object.fromEntries(promo.items.map((item) => [item.product, item.baseline]));
    setStart(promo.start_date);
    setEnd(promo.end_date);
    setConsStart(promo.cons_start);
    setConsEnd(promo.cons_end);
    setTactic(promo.tactic);
    setShowCreate(true);
  }
  async function savePromo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const result = await api<{ promotion: Promotion; overlap_warnings: string[] }>("/promotions", { method: "POST", body: JSON.stringify({
        ...(editing ? { id: editing.id, version: editing.version } : {}),
        market: props.market, customer_id: props.customerId, start_date: start, end_date: end,
        cons_start: consStart, cons_end: consEnd, tactic,
        items: Object.fromEntries(selectedProducts.map((code) => [code, totals[code] ?? 0])),
      }) });
      props.flash(editing ? "Promotion changes saved" : `Promotion ${result.promotion.promo_number} created in Entry status`);
      if (result.overlap_warnings.length) props.flash(`Overlapping promotion warning: ${result.overlap_warnings.join(", ")}`);
      setShowCreate(false);
      setEditing(null);
      reload();
    } catch (error) { props.setError(errorText(error)); }
  }
  async function statusAction(id: number, action: "save" | "confirm" | "approve" | "revert") {
    try {
      await api(`/promotions/${id}/${action}`, { method: "POST" });
      const messages = {
        save: "Promotion moved to Planned",
        confirm: "Promotion sent for approval",
        approve: "Promotion approved",
        revert: "Future promotion reverted to Planned for editing",
      };
      props.flash(messages[action]);
      reload();
    } catch (error) { props.setError(errorText(error)); }
  }
  const canEdit = props.user.role === "PLANNER" || props.user.role === "APPROVER" || props.user.role === "ADMIN";
  const canApprove = props.user.role === "APPROVER" || props.user.role === "ADMIN";
  const statusLabels: Record<string, string> = {
    NEW: "Entry",
    SAVED: "Planned",
    CHANGED: "Approval Pending",
    APPROVED: "Approved",
  };
  const productsToAdd = available.filter((product) => !selectedProducts.includes(product.code));
  function addSelectedProduct() {
    if (!productToAdd || !baselines || selectedProducts.includes(productToAdd)) return;
    setSelectedProducts((current) => [...current, productToAdd]);
    setTotals((current) => ({ ...current, [productToAdd]: baselineFor(productToAdd) }));
    setProductToAdd("");
  }
  return <>
    <Heading title="Promotions" subtitle={`${props.market} · plan account ${props.customerId} · baseline is read-only; enter total cases`} actions={canEdit ? <button className="button primary" onClick={startCreate}>Create Promotion</button> : undefined} />
    {showCreate && <form className="panel form-grid" onSubmit={(event) => void savePromo(event)}>
      <div className="full-width"><h2>{editing ? `Edit ${editing.promo_number}` : "Create Promotion Entry"}</h2></div>
      <label>Start date<input required type="date" value={start} onChange={(event) => setStart(event.target.value)} /></label>
      <label>End date<input required type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></label>
      <label>Consumption start<input required type="date" value={consStart} onChange={(event) => setConsStart(event.target.value)} /></label>
      <label>Consumption end<input required type="date" value={consEnd} onChange={(event) => setConsEnd(event.target.value)} /></label>
      <label>Tactic<select required value={tactic} onChange={(event) => setTactic(event.target.value)}><option value="">Select tactic</option>{tactics.map((item) => <option key={item.name}>{item.name}</option>)}</select></label>
      <div className="product-picker full-width">
        <label htmlFor="promotion-product">Add listed product</label>
        <select id="promotion-product" disabled={!baselines || !productsToAdd.length} value={productToAdd} onChange={(event) => setProductToAdd(event.target.value)}>
          <option value="">{baselines === null ? "Loading baseline…" : productsToAdd.length ? "Choose a product" : "All listed products added"}</option>
          {productsToAdd.map((product) => <option key={product.code} value={product.code}>{product.description} · {product.code}</option>)}
        </select>
        <button className="button" disabled={!productToAdd || !baselines} onClick={addSelectedProduct} type="button">Add product</button>
      </div>
      <div className="table-scroll full-width"><table className="data-table"><thead><tr><th>P09 Product</th><th>Baseline</th><th>Total Cases</th><th>Uplift</th><th /></tr></thead><tbody>
        {selectedProducts.map((code) => {
          const product = available.find((item) => item.code === code);
          if (!product) return null;
          const baseline = baselineFor(code);
          const total = totals[code] ?? baseline;
          return <tr key={code}>
            <td>{product.description}<small>{product.code}</small></td>
            <td>{baseline}</td>
            <td><input aria-label={`Total cases for ${product.description}`} disabled={baselines === null} min={baseline} step="1" type="number" value={total} onChange={(event) => setTotals((current) => ({ ...current, [code]: Number(event.target.value) }))} /></td>
            <td>{total - baseline}</td>
            <td><button aria-label={`Remove ${product.description}`} className="text-button" onClick={() => {
              setSelectedProducts((current) => current.filter((selected) => selected !== code));
              setTotals((current) => {
                const next = { ...current };
                delete next[code];
                return next;
              });
            }} type="button">Remove</button></td>
          </tr>;
        })}
        {!selectedProducts.length && <tr><td className="empty-cell" colSpan={5}>Choose listed products above to enter total cases.</td></tr>}
      </tbody></table></div>
      <div className="form-actions full-width"><button className="button primary" disabled={!selectedProducts.length} type="submit">{editing ? "Save changes" : "Create Entry"}</button><button className="button" type="button" onClick={() => { setShowCreate(false); setEditing(null); }}>Cancel</button></div>
    </form>}
    <div className="table-scroll"><table className="data-table"><thead><tr><th>Promotion</th><th>Plan Account</th><th>Shipment</th><th>Tactic</th><th>Status</th><th>Baseline</th><th>Total</th><th>Uplift</th><th>Actions</th></tr></thead><tbody>
      {promotions.map((promo) => <Fragment key={promo.id}><tr id={`promotion-${promo.id}`}><td><button className="text-button" onClick={() => setExpanded((value) => { const next = new Set(value); next.has(promo.id) ? next.delete(promo.id) : next.add(promo.id); return next; })}>{expanded.has(promo.id) ? "−" : "+"} {promo.promo_number}</button></td><td>{promo.customer_name}</td><td>{promo.start_date} – {promo.end_date}</td><td>{promo.tactic}</td><td><span className={`status ${promo.status}`}>{statusLabels[promo.status] ?? promo.status}</span></td><td>{promo.baseline}</td><td>{promo.total}</td><td>{promo.uplift}</td><td className="action-cell">
        {canEdit && ["NEW", "SAVED"].includes(promo.status) && <button className="button" onClick={() => startEdit(promo)}>Edit</button>}
        {canEdit && promo.status === "NEW" && <button className="button primary" onClick={() => void statusAction(promo.id, "save")}>Save</button>}
        {canEdit && promo.status === "SAVED" && <button className="button" onClick={() => void statusAction(promo.id, "confirm")}>Confirm</button>}
        {canApprove && promo.status === "CHANGED" && <button className="button primary" onClick={() => void statusAction(promo.id, "approve")}>Approve</button>}
        {["PLANNER", "APPROVER", "ADMIN"].includes(props.user.role) && promo.status === "APPROVED" && promo.start_date > today() && <button className="button" onClick={() => void statusAction(promo.id, "revert")}>Revert to edit</button>}
      </td></tr>{expanded.has(promo.id) && promo.items.map((item) => <tr className="detail-row" key={`${promo.id}-${item.product}`}><td>{item.product}</td><td colSpan={2}>{item.description}</td><td colSpan={2}>Baseline {item.baseline} · Total {item.total}</td><td>{item.baseline}</td><td>{item.total}</td><td>Uplift {item.uplift}</td><td /></tr>)}</Fragment>)}
      {!promotions.length && <tr><td className="empty-cell" colSpan={9}>No promotions for this plan account.</td></tr>}
    </tbody></table></div>
  </>;
}

