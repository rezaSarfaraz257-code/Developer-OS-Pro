import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../services/api";
import "./AdvancedDashboard.css";

export default function AdvancedDashboardPage({ setPage }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { apiFetch("/workspace/summary/").then(r => r.json()).then(setData).catch(e => setError(e.message)); }, []);
  const bars = useMemo(() => data?.project_completion || [], [data]);
  return <main className="intelligence-page">
    <div className="intelligence-head"><div><span>LIVE WORKSPACE INTELLIGENCE</span><h2>Advanced dashboard</h2><p>Every metric below is calculated from your persisted projects, tasks and activity.</p></div><button onClick={() => setPage("dashboard")}>Back to workspace</button></div>
    {error && <div className="intel-error">{error}</div>}
    {!data ? <div className="intel-loading">Loading live telemetry…</div> : <>
      <section className="intel-stats">{[["Completion",`${data.completion}%`],["Active tasks",data.active_tasks],["Blocked",data.blocked_tasks],["Overdue",data.overdue_tasks],["Urgent",data.urgent_tasks]].map(([label,value]) => <article key={label}><small>{label}</small><strong>{value}</strong></article>)}</section>
      <section className="intel-grid"><div className="intel-card"><header><span>Project delivery</span><b>{bars.length} tracked</b></header>{bars.length ? bars.map(p => <div className="intel-bar" key={p.id}><div><span>{p.title}</span><b>{p.progress}%</b></div><i><em style={{width:`${p.progress}%`}}/></i><small>{p.tasks} tasks · {p.status}{p.deadline ? ` · due ${p.deadline}` : ""}</small></div>) : <p className="muted">Create a project to start measuring delivery.</p>}</div><div className="intel-card"><header><span>Signals</span><b>DERIVED</b></header><ul><li>{data.blocked_tasks ? `${data.blocked_tasks} blocked task(s) need attention.` : "No blocked tasks detected."}</li><li>{data.overdue_tasks ? `${data.overdue_tasks} overdue task(s) need triage.` : "No overdue active tasks detected."}</li><li>{data.completion >= 70 ? "Completion is above the 70% delivery threshold." : "Build smaller milestones to improve delivery visibility."}</li><li>{data.snippets} saved snippets and {data.notes} notes are available as project memory.</li></ul></div></section>
    </>}
  </main>;
}
