import { Fragment, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Heading } from "../components/Heading";
import { type BaselineData, type PageProps } from "../types";
import { downloadApiFile, encodeFile, errorText } from "../utils";

export function WeeklyVolume(props: PageProps) {
  const [data, setData] = useState<BaselineData | null>(null);
  const [values, setValues] = useState<Record<string, number>>({});
  const [dirty, setDirty] = useState(false);
  const baselineFileInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    api<BaselineData>(`/baseline?market=${props.market}&customer_id=${props.customerId}`)
      .then((result) => {
        setData(result);
        setValues(Object.fromEntries(result.products.flatMap((product) =>
          result.weeks.map((week, index) => [`${product.code}|${week}`, product.baseline[index] ?? 0]),
        )));
      })
      .catch((error: unknown) => props.setError(errorText(error)));
  }, [props.market, props.customerId, props.refresh, props.setError]);
  if (!data) return <p className="muted">Loading weekly volume…</p>;
  const products = data.products.filter((item) => props.products.some((product) => product.code === item.code));
  const weeks = data.weeks;
  async function save() {
    try {
      const cells = products.flatMap((product) =>
        weeks.map((week) => ({ product: product.code, week, qty_cs: values[`${product.code}|${week}`] ?? 0 })),
      );
      const result = await api<{ saved: number }>("/baseline", { method: "PUT", body: JSON.stringify({ market: props.market, customer_id: props.customerId, cells }) });
      setDirty(false);
      props.flash(`Saved ${result.saved} baseline cells`);
    } catch (error) { props.setError(errorText(error)); }
  }
  async function uploadBaseline(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".xlsx")) {
      props.setError("Select an XLSX baseline workbook.");
      return;
    }
    try {
      const result = await api<{ saved: number }>("/baseline/upload", {
        method: "POST",
        body: JSON.stringify({
          market: props.market,
          customer_id: props.customerId,
          filename: file.name,
          content_base64: await encodeFile(file),
        }),
      });
      setDirty(false);
      props.flash(`Loaded ${result.saved} weekly baseline values.`);
      props.refresh();
    } catch (error) { props.setError(errorText(error)); }
    finally {
      if (baselineFileInput.current) baselineFileInput.current.value = "";
    }
  }
  async function exportBaseline() {
    try {
      await downloadApiFile(
        `/baseline/export?market=${encodeURIComponent(props.market)}&customer_id=${props.customerId}`,
        `baseline_${props.market}_${props.customerId}.xlsx`,
      );
    } catch (error) { props.setError(errorText(error)); }
  }
  const canEdit = ["PLANNER", "APPROVER", "ADMIN"].includes(props.user.role);
  return <>
    <Heading title="Weekly Volume" subtitle={`${props.market} · ${products.length} listed products · baseline cases`} actions={<>
      <button className="button" onClick={() => void exportBaseline()}>Extract Baseline XLSX</button>
      {canEdit && <>
        <input ref={baselineFileInput} accept=".xlsx" className="visually-hidden" onChange={(event) => void uploadBaseline(event.target.files?.[0])} type="file" />
        <button className="button" onClick={() => baselineFileInput.current?.click()}>Load Baseline XLSX</button>
        <button className="button primary" disabled={!dirty} onClick={() => void save()}>Save baseline</button>
      </>}
    </>} />
    <div className="table-scroll"><table className="data-table wide-table"><thead><tr><th>Product</th><th>Row</th>{data.weeks.map((week) => <th key={week}>{week}</th>)}</tr></thead><tbody>
      {products.map((product) => <Fragment key={product.code}><tr><td className="sticky-product"><b>{product.description}</b><small>{product.brand} · {product.sub_brand} · {product.code}</small></td><td>FORECAST</td>{data.weeks.map((week) => <td key={week}><input className="volume-input" disabled={!canEdit} min="0" step="1" type="number" value={values[`${product.code}|${week}`] ?? 0} onChange={(event) => { setValues((current) => ({ ...current, [`${product.code}|${week}`]: Number(event.target.value) })); setDirty(true); }} /></td>)}</tr><tr className="actual-row"><td className="sticky-product">{product.description}<small>{product.code}</small></td><td>ACTUAL LY</td>{product.actual_last_year.map((value, index) => <td key={data.weeks[index]}>{value}</td>)}</tr></Fragment>)}
    </tbody></table></div>
  </>;
}

