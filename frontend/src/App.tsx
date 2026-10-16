import { useCallback, useEffect, useMemo, useState } from "react";
import { type User, api } from "./api";
import { LoginScreen } from "./components/LoginScreen";
import { pageNames } from "./constants";
import { PlanningPage } from "./pages/PlanningPage";
import { Configuration } from "./pages/configuration/Configuration";
import { type Bootstrap, type ConfigTab, type Page } from "./types";
import { errorText } from "./utils";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [page, setPage] = useState<Page>("weekly");
  const [configTab, setConfigTab] = useState<ConfigTab>("access");
  const [market, setMarket] = useState("");
  const [customerId, setCustomerId] = useState(0);
  const [revision, setRevision] = useState(0);
  const [calendarPromotionId, setCalendarPromotionId] = useState<number | null>(null);
  const [ssoEnabled, setSsoEnabled] = useState(false);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  const reloadBootstrap = useCallback(async () => {
    const data = await api<Bootstrap & { user: User }>("/bootstrap");
    setBootstrap(data);
    if (data.markets.length) {
      const selectedMarket = data.markets.find((item) => item.code === "DE")?.code ?? data.markets[0].code;
      setMarket(selectedMarket);
      setCustomerId(data.customers.find((item) => item.market_code === selectedMarket)?.id
        ?? data.customers[0]?.id ?? 0);
    }
  }, []);
  const refreshConfiguration = useCallback(() => {
    setRevision((value) => value + 1);
    void reloadBootstrap().catch((reason: unknown) => setError(errorText(reason)));
  }, [reloadBootstrap]);

  const enterApp = useCallback(
    async (authenticatedUser: User) => {
      setUser(authenticatedUser);
      await reloadBootstrap();
      setError("");
    },
    [reloadBootstrap],
  );

  useEffect(() => {
    let active = true;
    Promise.all([
      api<User>("/auth/me").catch(() => null),
      api<{ enabled: boolean }>("/auth/sso/status").catch(() => ({ enabled: false })),
    ])
      .then(async ([authenticatedUser, sso]) => {
        if (!active) return;
        setSsoEnabled(sso.enabled);
        if (authenticatedUser) {
          await enterApp(authenticatedUser);
          if (new URLSearchParams(window.location.search).get("sso") === "created_admin") {
            setNotice("Your account is the first ArBa account and has been made an administrator.");
          }
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(errorText(reason));
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [enterApp]);

  useEffect(() => {
    setError("");
  }, [page, configTab]);

  const currentMarket = bootstrap?.markets.find((item) => item.code === market);
  const customers = useMemo(
    () => bootstrap?.customers.filter((item) => item.market_code === market) ?? [],
    [bootstrap?.customers, market],
  );

  async function authenticate(path: "/auth/login" | "/auth/signup", body: object) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ user: User; first_user_admin?: boolean }>(path, {
        method: "POST",
        body: JSON.stringify(body),
      });
      await enterApp(result.user);
      if (path === "/auth/signup") {
        setNotice(result.first_user_admin
          ? "Your account is the first ArBa account and has been made an administrator."
          : "Account created. An administrator must assign your role and plan-account access.");
      }
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
      setBootstrap(null);
      setPage("weekly");
      setConfigTab("access");
      setNotice("");
    }
  }

  function flash(message: string) {
    setNotice(message);
    window.setTimeout(() => setNotice(""), 4500);
  }

  if (!user) {
    return (
      <LoginScreen
        busy={busy}
        error={error}
        ssoEnabled={ssoEnabled}
        onAuthenticate={authenticate}
      />
    );
  }
  if (!bootstrap) {
    return <main className="center-state">Loading your ArBa workspace…</main>;
  }
  const visibleProducts = bootstrap.products;
  const isSystemAdmin = user.role === "ADMIN";
  const isArbaAdmin = isSystemAdmin || Boolean(user.admin_sales_org_access?.length);
  if (!isArbaAdmin && bootstrap.markets.length === 0) {
    return (
      <main className="access-pending">
        <header className="topbar"><strong className="wordmark">ArBa</strong><button className="button" onClick={signOut}>Sign out</button></header>
        <section className="pending-card">
          <span className="eyebrow">ACCESS PENDING</span>
          <h1>Your account is ready</h1>
          <p>An ArBa administrator must assign your sales organization and plan accounts before planning data is available.</p>
          <button className="button primary" onClick={() => void reloadBootstrap()}>Check access again</button>
        </section>
      </main>
    );
  }

  const planningPages: Page[] = ["weekly", "promotions", "calendar", "history", "report", "listing"];
  const activePage = page;
  function navigatePlanningPage(nextPage: Page) {
    setPage(nextPage);
  }

  return (
    <div className="app-shell">
      <header className="topbar app-topbar">
        <strong className="wordmark">ArBa</strong>
        <span className="product-title">Promo Volume Predictor</span>
        <span className="topbar-spacer" />
        <span className="user-name">{user.name}</span>
        <span className="role-pill">{isArbaAdmin && !isSystemAdmin ? "ORG ADMIN" : user.role}</span>
        <button className="button" onClick={signOut}>Sign out</button>
      </header>
      <div className="workspace">
        <aside className="sidebar">
          <p className="nav-caption">PLANNING</p>
          {planningPages.map((item) => (
            <button
              className={`nav-button ${activePage === item ? "selected" : ""}`}
              key={item}
              onClick={() => navigatePlanningPage(item)}
            >
              {pageNames[item]}
            </button>
          ))}
          {isArbaAdmin && (
            <>
              <p className="nav-caption">CONFIGURATION</p>
              <button
                className={`nav-button ${page === "configuration" ? "selected" : ""}`}
                onClick={() => setPage("configuration")}
              >
                Configuration
              </button>
            </>
          )}
        </aside>
        <main className="main-content">
          {page !== "configuration" && <section className="selection-bar">
            <label>Market<select value={market} onChange={(event) => {
              const next = event.target.value;
              setMarket(next);
              const nextCustomer = bootstrap.customers.find((item) => item.market_code === next);
              if (nextCustomer) setCustomerId(nextCustomer.id);
            }}>
              {bootstrap.markets.map((item) => <option key={item.code} value={item.code}>{item.code} · {item.name}</option>)}
            </select></label>
            <label>Plan Account<select value={customerId} onChange={(event) => setCustomerId(Number(event.target.value))}>
              {customers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select></label>
          </section>}
          {error && <div role="alert" className="alert error-alert">{error}<button aria-label="Dismiss" onClick={() => setError("")}>×</button></div>}
          {notice && <div role="status" className="alert success-alert">{notice}</div>}
          {page === "configuration" && isArbaAdmin ? (
            <Configuration
              key={configTab}
              activeTab={configTab}
              setActiveTab={setConfigTab}
              isSystemAdmin={isSystemAdmin}
              bootstrap={bootstrap}
              flash={flash}
              setError={setError}
              refresh={refreshConfiguration}
            />
          ) : (
            <PlanningPage
              key={`${activePage}-${market}-${customerId}-${revision}`}
              page={activePage}
              market={market}
              customerId={customerId}
              user={user}
              bootstrap={bootstrap}
              products={visibleProducts}
              flash={flash}
              setError={setError}
              refresh={refresh}
              openPromotionId={calendarPromotionId}
              onPromotionOpened={() => setCalendarPromotionId(null)}
              onOpenPromotion={(promotionId) => {
                setCalendarPromotionId(promotionId);
                setPage("promotions");
              }}
            />
          )}
        </main>
      </div>
    </div>
  );
}

