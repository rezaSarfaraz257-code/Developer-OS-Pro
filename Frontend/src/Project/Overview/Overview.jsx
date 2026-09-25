import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../services/api";
import "./Overview.css";

function daysUntil(value) {
  if (!value) return null;
  const target = new Date(`${value}T23:59:59`);
  if (Number.isNaN(target.getTime())) return null;
  return Math.ceil((target.getTime() - Date.now()) / 86400000);
}

export default function OverviewPage({ setPage, project = {} }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(Boolean(project?.id));
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    if (!project?.id) {
      setTasks([]);
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    apiFetch(`/tasks/?project=${project.id}`)
      .then((response) => response.json())
      .then((data) => {
        if (active) setTasks(Array.isArray(data) ? data.filter((task) => task.project === project.id) : []);
      })
      .catch((err) => active && setError(err.message || "Unable to load project telemetry."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [project?.id]);

  const metrics = useMemo(() => {
    const total = tasks.length || Number(project?.task_count || 0);
    const done = tasks.filter((task) => task.status === "done").length;
    const blocked = tasks.filter((task) => task.status === "blocked").length;
    const overdue = tasks.filter((task) => task.due_date && task.status !== "done" && new Date(`${task.due_date}T23:59:59`) < new Date()).length;
    const completion = total ? Math.round((done / total) * 100) : Number(project?.progress || 0);
    const days = daysUntil(project?.deadline);
    const risk = blocked || overdue ? "Attention" : days !== null && days <= 3 && completion < 80 ? "Tight" : "Stable";
    return [
      { label: "Delivery", value: `${completion}%`, detail: `${done}/${total} tasks complete`, tone: "cyan" },
      { label: "Active", value: Math.max(total - done, 0), detail: "unfinished tasks", tone: "violet" },
      { label: "Blocked", value: blocked, detail: blocked ? "needs triage" : "no blockers", tone: blocked ? "red" : "green" },
      { label: "Timeline", value: days === null ? "—" : days < 0 ? `${Math.abs(days)}d late` : `${days}d`, detail: project?.deadline ? "to deadline" : "no deadline", tone: days !== null && days < 0 ? "red" : "green" },
      { label: "Signal", value: risk, detail: "derived from workspace data", tone: risk === "Stable" ? "green" : "red" },
    ];
  }, [project, tasks]);

  const highlights = useMemo(() => {
    const items = [];
    const done = tasks.filter((task) => task.status === "done").length;
    const blocked = tasks.filter((task) => task.status === "blocked").length;
    const overdue = tasks.filter((task) => task.due_date && task.status !== "done" && new Date(`${task.due_date}T23:59:59`) < new Date()).length;
    if (blocked) items.push(`${blocked} blocked task${blocked > 1 ? "s" : ""} should be triaged before new work.`);
    if (overdue) items.push(`${overdue} overdue task${overdue > 1 ? "s" : ""} ${overdue > 1 ? "are" : "is"} still active.`);
    if (!blocked && !overdue) items.push("No blocked or overdue work is currently detected.");
    if (tasks.length) items.push(`${done} of ${tasks.length} task${tasks.length > 1 ? "s" : ""} completed; delivery is calculated from persisted task state.`);
    if (project?.deadline) items.push(`Project deadline: ${project.deadline}. Keep the next milestone small and explicit.`);
    if (!tasks.length) items.push("Add a few concrete tasks to unlock richer delivery telemetry.");
    return items.slice(0, 4);
  }, [project, tasks]);

  return (
    <main className="overview-page">
      <div className="overview-head">
        <div>
          <span>LIVE PROJECT TELEMETRY</span>
          <h2>{project?.title || "Project overview"}</h2>
          <p>Every signal on this screen is derived from your persisted project and task data.</p>
        </div>
        <button type="button" onClick={() => setPage("dashboard")}>Back to workspace</button>
      </div>

      {error && <div className="overview-error">{error}</div>}

      <section className="overview-metrics">
        {metrics.map((metric) => (
          <article className={`overview-metric ${metric.tone}`} key={metric.label}>
            <small>{metric.label}</small>
            <strong>{loading ? "…" : metric.value}</strong>
            <span>{metric.detail}</span>
          </article>
        ))}
      </section>

      <section className="overview-grid">
        <div className="overview-card overview-summary">
          <div className="overview-card-head"><span>Project context</span><b>{project?.category || "GENERAL"}</b></div>
          <h3>{project?.title || "Developer OS"}</h3>
          <p>{project?.description || "A focused engineering workspace for planning, execution, reusable knowledge and delivery visibility."}</p>
          <div className="overview-meta">
            <span>Status <b>{project?.status || "Planning"}</b></span>
            <span>Priority <b>{project?.priority || "medium"}</b></span>
            <span>Deadline <b>{project?.deadline || "Not set"}</b></span>
          </div>
        </div>
        <div className="overview-card">
          <div className="overview-card-head"><span>Signals</span><b>DERIVED</b></div>
          <ul className="overview-highlights">
            {highlights.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      </section>
    </main>
  );
}
