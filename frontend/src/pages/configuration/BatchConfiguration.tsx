import { useEffect, useState, type FormEvent } from "react";
import { api } from "../../api";
import { weekdays } from "../../constants";
import { type Pipeline } from "../../types";
import { errorText } from "../../utils";

export function BatchConfiguration(props: {
  flash: (message: string) => void;
  setError: (message: string) => void;
}) {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [runs, setRuns] = useState<Record<string, Record<string, unknown>[]>>({});
  const [revision, setRevision] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    api<{ pipelines: Pipeline[] }>("/admin/pipelines").then((result) => setPipelines(result.pipelines))
      .catch((error: unknown) => props.setError(errorText(error)));
  }, [props.setError, revision]);
  function update(id: string, changes: Partial<Pipeline>) {
    setPipelines((current) => current.map((item) => item.id === id ? { ...item, ...changes } : item));
  }
  async function save(pipeline: Pipeline) {
    try {
      await api(`/admin/pipelines/${pipeline.id}`, {
        method: "PUT",
        body: JSON.stringify({
          enabled: pipeline.enabled,
          schedule_frequency: pipeline.schedule_frequency,
          schedule_timezone: pipeline.schedule_timezone,
          schedule_time: pipeline.schedule_time,
          schedule_weekday: pipeline.schedule_weekday,
          schedule_month_day: pipeline.schedule_month_day,
          schedule_quarter_month: pipeline.schedule_quarter_month,
          schedule_start_date: pipeline.schedule_start_date || null,
          schedule_end_date: pipeline.schedule_end_date || null,
          file_path: pipeline.config_json.file_path ?? "",
        }),
      });
      props.flash(`Saved schedule for ${pipeline.id}`);
      setRevision((value) => value + 1);
    } catch (error) { props.setError(errorText(error)); }
  }
  async function createPipeline(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setCreating(true);
    try {
      const result = await api<{ id: string }>("/admin/pipelines", {
        method: "POST",
        body: JSON.stringify({
          name: values.get("name"),
          direction: values.get("direction"),
          source: values.get("source"),
          target: values.get("target"),
          connector_type: values.get("connector_type"),
          file_path: values.get("file_path"),
          enabled: (form.elements.namedItem("enabled") as HTMLInputElement).checked,
          schedule_frequency: values.get("schedule_frequency"),
          schedule_timezone: values.get("schedule_timezone"),
          schedule_time: values.get("schedule_time"),
          schedule_weekday: Number(values.get("schedule_weekday")),
          schedule_month_day: Number(values.get("schedule_month_day")),
          schedule_quarter_month: Number(values.get("schedule_quarter_month")),
          schedule_start_date: values.get("schedule_start_date") || null,
          schedule_end_date: values.get("schedule_end_date") || null,
        }),
      });
      props.flash(`Created pipeline ${result.id}`);
      setShowCreate(false);
      setRevision((value) => value + 1);
    } catch (error) { props.setError(errorText(error)); }
    finally { setCreating(false); }
  }
  async function runNow(id: string) {
    try {
      const result = await api<{ run_id: number; status: string; message: string }>(`/admin/pipelines/${id}/run?dry_run=${dryRun}`, { method: "POST" });
      props.flash(`Run #${result.run_id}: ${result.status} · ${result.message}`);
      setRevision((value) => value + 1);
    } catch (error) { props.setError(errorText(error)); }
  }
  async function showRuns(id: string) {
    try {
      const result = await api<{ runs: Record<string, unknown>[] }>(`/admin/pipelines/${id}/runs`);
      setRuns((current) => ({ ...current, [id]: result.runs }));
    } catch (error) { props.setError(errorText(error)); }
  }
  return <section className="config-section">
    <div className="panel-heading"><div><h2>Batch Job Configuration</h2><p>Create, schedule, enable, and manually run inbound or outbound pipelines.</p></div><button className="button primary" onClick={() => setShowCreate((value) => !value)}>{showCreate ? "Close" : "Create Pipeline"}</button></div>
    <div className="schedule-explainer"><b>Pipeline schedules</b><span>Choose the local timezone and run time. Monthly and quarterly jobs use the selected calendar date; the last day is used when a month is shorter. Start/end dates limit the period during which the job runs.</span></div>
    {showCreate && <form className="panel" onSubmit={(event) => void createPipeline(event)}>
      <div className="panel-heading"><div><h2>New pipeline</h2><p>File locations are relative to the ArBa Files folder. SAP OData, SFTP, and REST connectors require their corresponding integration configuration.</p></div></div>
      <div className="schedule-grid">
        <label>Pipeline name<input maxLength={120} minLength={2} name="name" required /></label>
        <label>Direction<select name="direction"><option value="INBOUND">INBOUND · consume into ArBa</option><option value="OUTBOUND">OUTBOUND · send from ArBa</option></select></label>
        <label>Source<input defaultValue="SAP S/4HANA" name="source" required /></label>
        <label>Target<input defaultValue="ArBa" name="target" required /></label>
        <label>Connector<select name="connector_type">{["FileConnector", "MockSapConnector", "MockP10Connector", "SapOdataConnector", "SftpConnector", "RestConnector"].map((connector) => <option key={connector}>{connector}</option>)}</select></label>
        <label>File location<input name="file_path" placeholder="Inbound Queue/file.csv or Outbound/file.csv" /></label>
        <label>Frequency<select defaultValue="DAILY" name="schedule_frequency">{["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY"].map((frequency) => <option key={frequency}>{frequency}</option>)}</select></label>
        <label>Timezone (IANA)<input defaultValue="UTC" name="schedule_timezone" required /></label>
        <label>Run time<input defaultValue="02:00" name="schedule_time" type="time" required /></label>
        <label>Weekday<select defaultValue="1" name="schedule_weekday">{weekdays.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label>
        <label>Day of month<input defaultValue="1" max="31" min="1" name="schedule_month_day" type="number" /></label>
        <label>Month of quarter<select defaultValue="1" name="schedule_quarter_month"><option value="1">First month</option><option value="2">Second month</option><option value="3">Third month</option></select></label>
        <label>Start date<input name="schedule_start_date" type="date" /></label>
        <label>End date<input name="schedule_end_date" type="date" /></label>
        <label className="toggle-label"><input name="enabled" type="checkbox" /> Enabled</label>
      </div>
      <div className="action-row"><button className="button primary" disabled={creating} type="submit">{creating ? "Creating…" : "Create Pipeline"}</button><button className="button" onClick={() => setShowCreate(false)} type="button">Cancel</button></div>
    </form>}
    <label className="inline-label dry-run-toggle"><input checked={dryRun} onChange={(event) => setDryRun(event.target.checked)} type="checkbox" /> Dry run (preview only)</label>
    {pipelines.map((pipeline) => <article className="panel pipeline-card" key={pipeline.id}>
      <div className="panel-heading"><div><h2>{pipeline.id} · {pipeline.name}</h2><p>{pipeline.source} → {pipeline.target} · {pipeline.connector_type}</p></div><label className="toggle-label"><input checked={pipeline.enabled} onChange={(event) => update(pipeline.id, { enabled: event.target.checked })} type="checkbox" /> Enabled</label></div>
      <div className="schedule-grid">
        <label>Frequency<select value={pipeline.schedule_frequency} onChange={(event) => update(pipeline.id, { schedule_frequency: event.target.value as Pipeline["schedule_frequency"] })}>{["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY"].map((frequency) => <option key={frequency}>{frequency}</option>)}</select></label>
        <label>Timezone (IANA)<input value={pipeline.schedule_timezone} onChange={(event) => update(pipeline.id, { schedule_timezone: event.target.value })} placeholder="Europe/Berlin" /></label>
        <label>Run time<input type="time" value={pipeline.schedule_time} onChange={(event) => update(pipeline.id, { schedule_time: event.target.value })} /></label>
        <label>Weekday<select value={pipeline.schedule_weekday} onChange={(event) => update(pipeline.id, { schedule_weekday: Number(event.target.value) })}>{weekdays.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label>
        <label>Day of month<input max="31" min="1" type="number" value={pipeline.schedule_month_day} onChange={(event) => update(pipeline.id, { schedule_month_day: Number(event.target.value) })} /></label>
        <label>Month of quarter<select value={pipeline.schedule_quarter_month} onChange={(event) => update(pipeline.id, { schedule_quarter_month: Number(event.target.value) })}><option value="1">First month</option><option value="2">Second month</option><option value="3">Third month</option></select></label>
        <label>Start date<input type="date" value={pipeline.schedule_start_date ?? ""} onChange={(event) => update(pipeline.id, { schedule_start_date: event.target.value || null })} /></label>
        <label>End date<input type="date" value={pipeline.schedule_end_date ?? ""} onChange={(event) => update(pipeline.id, { schedule_end_date: event.target.value || null })} /></label>
        <label>File location (relative to ArBa Files)<input value={pipeline.config_json?.file_path ?? ""} onChange={(event) => update(pipeline.id, { config_json: { ...pipeline.config_json, file_path: event.target.value } })} placeholder="Inbound Queue/file.csv or Outbound/file.csv" /></label>
      </div>
      <p className="schedule-status">Next run: {pipeline.next_run_at ? new Date(pipeline.next_run_at).toLocaleString() : "Not scheduled"} · Last run: {pipeline.last_run?.finished_at ?? "Never"}</p>
      <div className="action-row"><button className="button primary" onClick={() => void save(pipeline)}>Save pipeline</button><button className="button" onClick={() => void runNow(pipeline.id)}>{dryRun ? "Run now (dry run)" : "Run now"}</button><button className="button" onClick={() => void showRuns(pipeline.id)}>Run history</button></div>
      {runs[pipeline.id] && <div className="run-history">{runs[pipeline.id].map((run, index) => <p key={String(run.id ?? index)}>Run #{String(run.id)} · {String(run.trigger)} · {String(run.status)} · {String(run.message ?? "")}</p>)}</div>}
    </article>)}
  </section>;
}

