import { useEffect, useState, type FormEvent } from "react";
import { api } from "../../api";
import { editableRoles, roles } from "../../constants";
import { type AccessData, type Bootstrap } from "../../types";
import { accountValues, assignmentKey, errorText, multiValues } from "../../utils";

export function AccessManagement(props: {
  bootstrap: Bootstrap;
  flash: (message: string) => void;
  setError: (message: string) => void;
  isSystemAdmin: boolean;
}) {
  const [data, setData] = useState<AccessData | null>(null);
  const [revision, setRevision] = useState(0);
  const [formRevision, setFormRevision] = useState(0);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    api<AccessData>("/admin/users").then((result) => {
      setData(result);
      setFormRevision((value) => value + 1);
    }).catch((error: unknown) => props.setError(errorText(error)));
  }, [props.setError, revision]);
  if (!data) return <p className="muted">Loading access management…</p>;

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    const salesOrgSelect = form.elements.namedItem("sales_org_access") as HTMLSelectElement;
    const accountSelect = form.elements.namedItem("assignments") as HTMLSelectElement;
    const activeInput = form.elements.namedItem("active") as HTMLInputElement;
    setCreating(true);
    try {
      const created = await api<{
        id: number;
        email: string;
        role: string;
        first_admin_sales_orgs: string[];
      }>("/admin/users", {
        method: "POST",
        body: JSON.stringify({
          email: values.get("email"),
          name: values.get("name"),
          role: values.get("role"),
          password: values.get("password"),
          active: activeInput.checked,
          sales_org_access: multiValues(salesOrgSelect),
          assignments: accountValues(accountSelect),
          admin_sales_org_access: multiValues(form.elements.namedItem("admin_sales_org_access") as HTMLSelectElement),
        }),
      });
      const firstOrgList = created.first_admin_sales_orgs.length
        ? ` First administrator for ${created.first_admin_sales_orgs.join(", ")}.`
        : "";
      props.flash(`Created User ID ${created.id} · ${created.email}.${firstOrgList}`);
      form.reset();
      setShowCreate(false);
      setRevision((value) => value + 1);
    } catch (error) { props.setError(errorText(error)); }
    finally { setCreating(false); }
  }

  async function saveUser(event: FormEvent<HTMLFormElement>, userId: number) {
    event.preventDefault();
    const form = event.currentTarget;
    const salesOrgSelect = form.elements.namedItem("sales_org_access") as HTMLSelectElement;
    const accountSelect = form.elements.namedItem("assignments") as HTMLSelectElement;
    const roleSelect = form.elements.namedItem("role") as HTMLSelectElement;
    const activeInput = form.elements.namedItem("active") as HTMLInputElement;
    const adminSalesOrgSelect = form.elements.namedItem("admin_sales_org_access") as HTMLSelectElement;
    try {
      const result = await api<{ first_admin_sales_orgs: string[] }>(`/admin/users/${userId}`, {
        method: "PUT",
        body: JSON.stringify({
          role: roleSelect.value,
          active: activeInput.checked,
          sales_org_access: multiValues(salesOrgSelect),
          assignments: accountValues(accountSelect),
          admin_sales_org_access: multiValues(adminSalesOrgSelect),
        }),
      });
      const firstOrgMessage = result.first_admin_sales_orgs.length
        ? ` First administrator for ${result.first_admin_sales_orgs.join(", ")}.`
        : "";
      props.flash(`Access updated for User ID ${userId}.${firstOrgMessage}`);
      setRevision((value) => value + 1);
    } catch (error) { props.setError(errorText(error)); }
  }

  return <section className="config-section">
    <div className="panel">
      <div className="panel-heading"><div><h2>Create User ID</h2><p>Create a user and assign role, organization, and plan-account access.</p></div><div className="action-row"><span className="count-pill">{data.users.length} users</span><button className="button primary" onClick={() => setShowCreate(true)}>Create User</button></div></div>
    </div>
    {showCreate && <div className="modal-backdrop" role="presentation">
      <section aria-labelledby="create-user-title" aria-modal="true" className="panel create-user-modal" role="dialog">
        <div className="panel-heading"><div><h2 id="create-user-title">Create User</h2><p>Choose access. Use Ctrl/Cmd to select or deselect multiple values.</p></div><button aria-label="Close" className="button" onClick={() => setShowCreate(false)} type="button">Close</button></div>
        <form className="config-form" onSubmit={(event) => void createUser(event)}>
          <label>Email ID<input autoComplete="email" maxLength={254} name="email" required type="email" /></label>
          <label>User Name<input maxLength={100} minLength={2} name="name" required /></label>
          <label>ArBa Role<select defaultValue="PLANNER" name="role">{roles.map((role) => <option key={role}>{role}</option>)}</select></label>
          <label>Initial password<input autoComplete="new-password" minLength={12} name="password" required type="password" /></label>
          <label>Sales Organization Access<select multiple name="sales_org_access" required size={4}>{data.sales_orgs.map((item) => <option key={item.code} value={item.code}>{item.code} · {item.name}</option>)}</select></label>
          <label>ArBa Administrator Access<select multiple name="admin_sales_org_access" size={4}>{data.sales_orgs.map((item) => <option key={item.code} value={item.code}>{item.code} · {item.name}</option>)}</select><small>Must also be selected under Sales Organization Access.</small></label>
          <label>Plan Account Access<select multiple name="assignments" size={4}>{props.bootstrap.customers.map((item) => <option key={item.id} value={assignmentKey({ market_code: item.market_code, customer_id: item.id })}>{item.market_code} · {item.name}</option>)}</select><small>Accounts must belong to the selected sales organizations.</small></label>
          <label className="active-control"><input defaultChecked name="active" type="checkbox" /> User Active</label>
          <div className="form-actions"><button className="button primary" disabled={creating} type="submit">{creating ? "Creating…" : "Create User"}</button><button className="button" onClick={() => setShowCreate(false)} type="button">Cancel</button></div>
        </form>
      </section>
    </div>}
    <div className="panel">
      <div className="panel-heading"><div><h2>Access Management</h2><p>Inactive users are automatically deactivated after 30 days without a successful sign-in.</p></div></div>
      <div className="user-access-list">
        {data.users.map((user) => {
          const accountSet = new Set(data.assignments.filter((item) => item.user_id === user.id).map(assignmentKey));
          return <form className="user-access-row" key={`${user.id}-${formRevision}`} onSubmit={(event) => void saveUser(event, user.id)}>
            <div className="user-identity"><b>User ID {user.id}</b><span>{user.email}</span><small>{user.name}</small><span className={`status ${user.active ? "ACTIVE" : "INACTIVE"}`}>{user.active ? "Active" : "Inactive"}</span><small>Last login: {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "Never"}</small></div>
            <label>ArBa Role<select defaultValue={user.role} name="role">{editableRoles.map((role) => <option key={role}>{role}</option>)}</select></label>
            <label>Sales Organization Access<select defaultValue={user.sales_org_access} multiple name="sales_org_access" size={3}>{data.sales_orgs.map((item) => <option key={item.code} value={item.code}>{item.code} · {item.name}</option>)}</select></label>
            <label>ArBa Administrator Access<select defaultValue={user.admin_sales_org_access} multiple name="admin_sales_org_access" size={3}>{data.sales_orgs.map((item) => <option key={item.code} value={item.code}>{item.code} · {item.name}</option>)}</select></label>
            <label>Plan Account Access<select defaultValue={[...accountSet]} multiple name="assignments" size={3}>{props.bootstrap.customers.map((item) => <option key={item.id} value={assignmentKey({ market_code: item.market_code, customer_id: item.id })}>{item.market_code} · {item.name}</option>)}</select></label>
            <label className="active-control"><input defaultChecked={user.active} name="active" type="checkbox" /> Active</label>
            <button className="button" type="submit">Save access</button>
          </form>;
        })}
      </div>
    </div>
  </section>;
}

