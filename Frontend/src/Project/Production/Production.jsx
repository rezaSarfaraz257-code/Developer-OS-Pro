import { useEffect, useState } from "react";
import { API_URL, getAccessToken } from "../../services/api";

export default function ProductionPage({ setPage }) {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [checkedAt, setCheckedAt] = useState(null);

  const checkHealth = async () => {
    setError("");
    try {
      const response = await fetch(`${API_URL}/health/`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "Health check failed.");
      setHealth(payload);
      setCheckedAt(new Date());
    } catch (err) {
      setHealth(null);
      setCheckedAt(new Date());
      setError(err.message);
    }
  };

  useEffect(() => { checkHealth(); }, []);

  const checks = [
    { label: "API health", ok: health?.status === "ok", detail: health?.database === "ok" ? "API and database responding" : "Database status unavailable" },
    { label: "Authenticated session", ok: Boolean(getAccessToken()), detail: getAccessToken() ? "Active browser session" : "No active session" },
    { label: "Release version", ok: Boolean(health?.version), detail: health?.version ? `Version ${health.version}` : "Version unavailable" },
    { label: "Deployment verification", ok: null, detail: "Run CI and the release gate on the target environment" },
    { label: "TLS / domain", ok: null, detail: "Verify HTTPS, DNS, proxy headers and HSTS at the deployment edge" },
    { label: "Observability", ok: null, detail: "Connect application logs, error tracking and telemetry in production" },
  ];

  return (
    <main className="page-panel" style={{ background: "rgba(10, 17, 29, 0.9)", border: "1px solid rgba(148, 163, 184, 0.2)", borderRadius: 24, padding: 24 }}>
      <div className="page-header-row" style={{ marginBottom: 22 }}>
        <div>
          <span className="eyebrow" style={{ color: "#fbbf24", letterSpacing: "0.14em", textTransform: "uppercase", fontSize: 11, display: "inline-block", marginBottom: 8 }}>Production</span>
          <h2 style={{ margin: 0, fontSize: 30 }}>Production readiness</h2>
          <p style={{ color: "#9cb0c8", lineHeight: 1.7 }}>Runtime checks are live; infrastructure-only checks stay explicitly marked until they are verified on the target host.</p>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button type="button" className="secondary-button" onClick={checkHealth}>Recheck API</button>
          <button type="button" className="ghost-button" onClick={() => setPage("dashboard")}>Back to workspace</button>
        </div>
      </div>

      {error && <div role="alert" style={{ marginBottom: 16, color: "#fca5a5" }}>{error}</div>}
      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14 }}>
        {checks.map((item) => (
          <article key={item.label} style={{ background: "rgba(15, 23, 42, 0.82)", border: "1px solid rgba(148, 163, 184, 0.18)", borderRadius: 18, padding: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
              <strong>{item.label}</strong>
              <span style={{ fontWeight: 800, color: item.ok === true ? "#34d399" : item.ok === false ? "#fca5a5" : "#fbbf24" }}>{item.ok === true ? "PASS" : item.ok === false ? "FAIL" : "VERIFY"}</span>
            </div>
            <p style={{ margin: "10px 0 0", color: "#9cb0c8", lineHeight: 1.6 }}>{item.detail}</p>
          </article>
        ))}
      </section>
      {checkedAt && <small style={{ display: "block", marginTop: 16, color: "#71839a" }}>Last runtime check: {checkedAt.toLocaleTimeString()}</small>}
    </main>
  );
}
