import { useState } from "react";
import { api } from "../../api";
import { encodeFile, errorText } from "../../utils";

export function MasterDataConfig(props: {
  type: "customer" | "product";
  flash: (message: string) => void;
  setError: (message: string) => void;
  refresh: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [queued, setQueued] = useState<{ id: number; filename: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const customerMode = props.type === "customer";
  const title = customerMode ? "Customer Master" : "Product Master";
  const columns = customerMode
    ? ["Market Code or Sales Organization", "Plan Account Code L04", "Plan Account Name", "Parent L03"]
    : ["Product P09", "Product Description", "Brand", "Sub-brand", "Category", "Material Number", "Material Description (optional)", "Split Share (optional)"];

  async function upload() {
    if (!file) return props.setError("Select a CSV or XLSX extract first.");
    setBusy(true);
    try {
      const result = await api<{ id: number; filename: string; status: string; queue_folder: string }>(
        `/admin/master-data/${props.type}/upload`,
        { method: "POST", body: JSON.stringify({ filename: file.name, content_base64: await encodeFile(file) }) },
      );
      setQueued({ id: result.id, filename: result.filename });
      props.flash(`${result.filename} is in ${result.queue_folder}.`);
      props.refresh();
    } catch (error) { props.setError(errorText(error)); }
    finally { setBusy(false); }
  }

  async function process() {
    if (!queued) return;
    setBusy(true);
    try {
      const result = await api<{ rows: number }>(`/admin/files/${queued.id}/process`, { method: "POST" });
      props.flash(`${title} loaded: ${result.rows} rows processed.`);
      setQueued(null);
      setFile(null);
      props.refresh();
    } catch (error) { props.setError(errorText(error)); }
    finally { setBusy(false); }
  }

  return <section className="panel master-panel">
    <span className="eyebrow">SAP INBOUND</span>
    <h2>Load {title} extract</h2>
    <p>Upload a CSV or XLSX master-data extract. Files are staged in <b>Inbound Queue</b>; process performs validation and applies the entire extract atomically. Successfully processed files move to <b>Inbound Processed</b>.</p>
    <div className="required-fields"><b>Required columns</b><span>{columns.join(" · ")}</span></div>
    <label className="file-picker">Choose SAP extract<input accept=".csv,.xlsx" onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" /></label>
    {file && <p className="selected-file">{file.name} · {(file.size / 1024).toFixed(1)} KB</p>}
    <button className="button primary" disabled={busy || !file} onClick={() => void upload()}>{busy ? "Uploading…" : "Load to Inbound Queue"}</button>
    {queued && <div className="queue-confirm"><span>{queued.filename} is queued as file #{queued.id}.</span><button className="button primary" disabled={busy} onClick={() => void process()}>Validate and consume</button></div>}
  </section>;
}

