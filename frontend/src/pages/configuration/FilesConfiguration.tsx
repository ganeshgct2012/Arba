import { useEffect, useState } from "react";
import { api } from "../../api";
import { type ManagedFile } from "../../types";
import { errorText } from "../../utils";

export function FilesConfiguration(props: {
  flash: (message: string) => void;
  setError: (message: string) => void;
}) {
  const [files, setFiles] = useState<ManagedFile[]>([]);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    api<{ files: ManagedFile[] }>("/admin/files").then((result) => setFiles(result.files))
      .catch((error: unknown) => props.setError(errorText(error)));
  }, [props.setError, revision]);
  async function process(id: number) {
    try {
      const result = await api<{ rows: number }>(`/admin/files/${id}/process`, { method: "POST" });
      setRevision((value) => value + 1);
      props.flash(`Processed ${result.rows} master rows.`);
    } catch (error) { props.setError(errorText(error)); }
  }
  return <section className="panel">
    <div className="panel-heading"><div><h2>Inbound and outbound files</h2><p>Queued inbound files are in the Inbound Queue folder. Successfully consumed files appear in Inbound Processed. P10 exports are kept under Outbound.</p></div><button className="button" onClick={() => setRevision((value) => value + 1)}>Refresh</button></div>
    <div className="table-scroll"><table className="data-table"><thead><tr><th>Direction</th><th>Type</th><th>File</th><th>Status</th><th>Folder</th><th>Rows</th><th>Uploaded by</th><th>Created</th><th>Message</th><th>Actions</th></tr></thead><tbody>
      {files.map((file) => <tr key={file.id}><td>{file.direction}</td><td>{file.category}</td><td>{file.original_name}</td><td><span className={`status ${file.status}`}>{file.status}</span></td><td>{file.direction === "OUTBOUND" ? "Outbound" : file.status === "PROCESSED" ? "Inbound Processed" : "Inbound Queue"}</td><td>{file.row_count}</td><td>{file.uploaded_by}</td><td>{new Date(file.created_at).toLocaleString()}</td><td>{file.message}</td><td>{file.direction === "INBOUND" && ["QUEUED", "FAILED"].includes(file.status) && <button className="button primary" onClick={() => void process(file.id)}>Process</button>} <a className="button link-button" href={`/api/v1/admin/files/${file.id}/download`}>Download</a></td></tr>)}
      {!files.length && <tr><td className="empty-cell" colSpan={10}>No inbound or outbound files have been recorded.</td></tr>}
    </tbody></table></div>
  </section>;
}
