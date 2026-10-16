import { useState, type FormEvent } from "react";

export function LoginScreen(props: {
  busy: boolean;
  error: string;
  ssoEnabled: boolean;
  onAuthenticate: (path: "/auth/login" | "/auth/signup", body: object) => Promise<void>;
}) {
  const [registering, setRegistering] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const query = new URLSearchParams(window.location.search);
  const ssoError = query.get("sso_error");
  const ssoErrors: Record<string, string> = {
    cancelled: "Company SSO sign-in was cancelled.",
    authentication_failed: "Company SSO could not authenticate your account.",
    account_exists: "This email already has an ArBa account. Contact an administrator.",
    account_inactive: "This ArBa account is inactive.",
    invalid_state: "The SSO request expired. Please try again.",
  };

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void props.onAuthenticate(
      registering ? "/auth/signup" : "/auth/login",
      registering ? { name, email, password } : { email, password },
    );
  }

  return (
    <main className="login-page">
      <header className="topbar"><strong className="wordmark">ArBa</strong><span className="product-title">Promo Volume Predictor</span></header>
      <section className="login-layout">
        <div className="login-copy">
          <span className="eyebrow">EUROPEAN VOLUME PLANNING</span>
          <h1>Plan with clarity.<br />Deliver with confidence.</h1>
          <p>A single workspace for baseline planning, promotions, and weekly volume visibility across your markets.</p>
          <div className="market-chips"><span>DE</span><span>ES</span><span>PT</span><i /><span>CH</span><span>NL</span><span>AT</span><span>BE</span></div>
        </div>
        <section className="login-card">
          <span className="eyebrow">YOUR WORKSPACE</span>
          <h2>{registering ? "Create your ArBa account" : "Sign in to ArBa"}</h2>
          <p className="muted">{registering ? "Use your new account to sign in to ArBa." : "Use your ArBa account or company SSO to continue."}</p>
          {props.error && <p className="form-error" role="alert">{props.error}</p>}
          {ssoError && <p className="form-error" role="alert">{ssoErrors[ssoError] ?? "Company SSO could not complete sign-in."}</p>}
          {props.ssoEnabled && !registering && <button className="button sso-button" onClick={() => { window.location.href = "/api/v1/auth/sso/start"; }}>Sign in with company SSO</button>}
          <form onSubmit={submit}>
            {registering && <><label htmlFor="signup-name">User name</label><input autoComplete="name" id="signup-name" minLength={2} maxLength={100} onChange={(event) => setName(event.target.value)} required value={name} /></>}
            <label htmlFor="email">Email ID</label>
            <input autoComplete={registering ? "email" : "username"} id="email" onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" required type="email" value={email} />
            <label htmlFor="password">Password{registering && " (at least 12 characters)"}</label>
            <input autoComplete={registering ? "new-password" : "current-password"} id="password" minLength={registering ? 12 : undefined} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
            <button className="button primary wide" disabled={props.busy} type="submit">{props.busy ? "Please wait…" : registering ? "Create account" : "Sign in"}</button>
          </form>
          <button className="text-button" onClick={() => setRegistering((value) => !value)}>{registering ? "Back to sign in" : "New to ArBa? Create an account"}</button>
          {registering && <p className="muted small-note">The first account created becomes the ArBa administrator. Later accounts need access assigned by an administrator.</p>}
          {!props.ssoEnabled && <p className="muted small-note">Company SSO is not configured for this instance.</p>}
        </section>
      </section>
      <footer className="login-footer"><span>ARBA PROMO VOLUME PREDICTOR</span><span>From S/4HANA to P10 Arete</span></footer>
    </main>
  );
}

