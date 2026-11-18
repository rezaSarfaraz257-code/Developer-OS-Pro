import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../services/api";

const STAGES = ["Think", "Plan", "Design", "Build", "Test", "Debug", "Repair"];
const STATUS_LABELS = {
  todo: "Planned",
  in_progress: "In progress",
  blocked: "Blocked",
  done: "Completed",
};

function normalizeList(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.results)) return value.results;
  return [];
}

function dateLabel(value) {
  if (!value) return "No due date";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

export default function EngineeringControlCenter({ go }) {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("all");
  const [tasks, setTasks] = useState([]);
  const [activity, setActivity] = useState([]);
  const [mode, setMode] = useState("manual");
  const [statusFilter, setStatusFilter] = useState("all");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("medium");
  const [busy, setBusy] = useState(false);
  const [updatingId, setUpdatingId] = useState(null);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (!quiet) setError("");
    try {
      const [projectResponse, taskResponse, activityResponse] = await Promise.all([
        apiFetch("/projects/").then((r) => r.json()),
        apiFetch("/tasks/").then((r) => r.json()),
        apiFetch("/activity/").then((r) => r.json()),
      ]);
      setProjects(normalizeList(projectResponse));
      setTasks(normalizeList(taskResponse));
      setActivity(normalizeList(activityResponse));
      setLastUpdated(new Date());
    } catch (err) {
      if (!quiet) setError(err.message || "Unable to load engineering workspace data.");
    }
  }, []);

  useEffect(() => {
    load();
    const refreshId = window.setInterval(() => load({ quiet: true }), 20000);
    const onFocus = () => load({ quiet: true });
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(refreshId);
      window.removeEventListener("focus", onFocus);
    };
  }, [load]);

  const visibleTasks = useMemo(() => tasks.filter((task) => {
    const matchesProject = projectId === "all" || String(task.project) === projectId;
    const matchesStatus = statusFilter === "all" || task.status === statusFilter;
    return matchesProject && matchesStatus;
  }), [tasks, projectId, statusFilter]);

  const counts = useMemo(() => ({
    total: tasks.length,
    active: tasks.filter((task) => task.status === "in_progress").length,
    blocked: tasks.filter((task) => task.status === "blocked").length,
    completed: tasks.filter((task) => task.status === "done").length,
  }), [tasks]);

  const createTask = async (event) => {
    event.preventDefault();
    if (!title.trim() || projectId === "all") {
      setError(projectId === "all" ? "Select a project before creating a task." : "Task title is required.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await apiFetch("/tasks/", {
        method: "POST",
        body: JSON.stringify({
          project: Number(projectId),
          title: title.trim(),
          description: description.trim(),
          priority,
          status: "todo",
        }),
      });
      setTitle("");
      setDescription("");
      await load({ quiet: true });
    } catch (err) {
      setError(err.message || "Task could not be created.");
    } finally {
      setBusy(false);
    }
  };

  const updateTask = async (task, nextStatus) => {
    if (task.status === nextStatus) return;
    setUpdatingId(task.id);
    setError("");
    try {
      await apiFetch(`/tasks/${task.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      await load({ quiet: true });
    } catch (err) {
      setError(err.message || "Task status could not be updated.");
    } finally {
      setUpdatingId(null);
    }
  };

  const selectedProject = projects.find((project) => String(project.id) === projectId);
  const modeDetails = {
    manual: { title: "Manual Build", description: "Manage persisted project tasks directly. Status changes are saved through the workspace API.", available: true },
    agent: { title: "AI Agent Build", description: "No agent orchestration, run records or verification endpoint is exposed by this backend yet.", available: false },
    hybrid: { title: "Hybrid Build", description: "Coordinated human and agent execution requires the same missing orchestration contract.", available: false },
  }[mode];

  return (
    <div className="page engineering-page">
      <div className="hero-row engineering-hero">
        <div>
          <div className="eyebrow">DEVELOPER OS / ENGINEERING CONTROL</div>
          <h1>Engineering OS</h1>
          <p>Operate the software lifecycle from persisted project work, task state and recorded activity.</p>
        </div>
        <div className="engineering-sync">
          <span className="engineering-live-dot" />
          API SYNC
          <small>{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Waiting for data"}</small>
          <button className="ghost" onClick={() => load()} type="button">REFRESH</button>
        </div>
      </div>

      {error && <div className="error" role="alert">{error}</div>}

      <section className="engineering-mode-grid" aria-label="Build modes">
        {[
          { id: "manual", name: "Manual Build", note: "Persisted task control", enabled: true },
          { id: "agent", name: "AI Agent Build", note: "Backend orchestration unavailable", enabled: false },
          { id: "hybrid", name: "Hybrid Build", note: "Backend orchestration unavailable", enabled: false },
        ].map((item) => (
          <button
            type="button"
            key={item.id}
            className={`engineering-mode ${mode === item.id ? "selected" : ""} ${!item.enabled ? "unavailable" : ""}`}
            onClick={() => setMode(item.id)}
            aria-pressed={mode === item.id}
          >
            <span>{item.enabled ? "AVAILABLE" : "NOT CONNECTED"}</span>
            <strong>{item.name}</strong>
            <small>{item.note}</small>
          </button>
        ))}
      </section>

      <section className="engineering-stage-panel panel">
        <div className="panel-head">
          <div><span className="panel-kicker">ENGINEERING LIFECYCLE</span><h2>Think → Plan → Design → Build → Test → Debug → Repair</h2></div>
          <span className="engineering-source">Workflow reference · not an execution claim</span>
        </div>
        <div className="engineering-stages">
          {STAGES.map((stage, index) => (
            <div className="engineering-stage" key={stage}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <b>{stage}</b>
            </div>
          ))}
        </div>
        <p className={modeDetails.available ? "engineering-mode-note" : "engineering-mode-note warning"}>
          <strong>{modeDetails.title}:</strong> {modeDetails.description}
        </p>
      </section>

      <section className="engineering-metrics" aria-label="Workspace task totals">
        {[
          ["TASKS", counts.total],
          ["IN PROGRESS", counts.active],
          ["BLOCKED", counts.blocked],
          ["COMPLETED", counts.completed],
        ].map(([label, value]) => (
          <div className="stat-card" key={label}><span>{label}</span><strong>{value}</strong><small>Persisted task records</small></div>
        ))}
      </section>

      <div className="engineering-work-grid">
        <section className="panel">
          <div className="panel-head">
            <div><span className="panel-kicker">WORKSPACE CONTROL</span><h2>Execution queue</h2></div>
            <span className="engineering-source">{visibleTasks.length} shown</span>
          </div>
          <div className="engineering-filters">
            <label>PROJECT
              <select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
                <option value="all">All accessible projects</option>
                {projects.map((project) => <option value={String(project.id)} key={project.id}>{project.title}</option>)}
              </select>
            </label>
            <label>STATE
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">All states</option>
                <option value="todo">Planned</option>
                <option value="in_progress">In progress</option>
                <option value="blocked">Blocked</option>
                <option value="done">Completed</option>
              </select>
            </label>
          </div>
          <div className="engineering-task-list">
            {visibleTasks.map((task) => (
              <article className="engineering-task" key={task.id}>
                <div className="engineering-task-main">
                  <span className={`engineering-task-state state-${task.status}`}>{STATUS_LABELS[task.status] || task.status}</span>
                  <strong>{task.title}</strong>
                  <small>{task.project_title || projects.find((project) => String(project.id) === String(task.project))?.title || `Project #${task.project ?? "—"}`} · {task.priority} · Due {dateLabel(task.due_date)}</small>
                  {task.description && <p>{task.description}</p>}
                </div>
                <label className="engineering-status-control">
                  <span className="sr-only">Update status for {task.title}</span>
                  <select value={task.status} disabled={updatingId === task.id} onChange={(event) => updateTask(task, event.target.value)}>
                    <option value="todo">Planned</option>
                    <option value="in_progress">In progress</option>
                    <option value="blocked">Blocked</option>
                    <option value="done">Completed</option>
                  </select>
                </label>
              </article>
            ))}
            {!visibleTasks.length && <div className="empty">{tasks.length ? "No tasks match these filters." : "No persisted tasks found. Create a task for a project to populate this queue."}</div>}
          </div>
        </section>

        <aside className="engineering-side">
          <section className="panel">
            <span className="panel-kicker">TASK INTAKE</span>
            <h2>Create work item</h2>
            <p className="engineering-muted">Creates a real task record in the selected project.</p>
            <form className="engineering-create-form" onSubmit={createTask}>
              <label>PROJECT
                <select value={projectId} onChange={(event) => setProjectId(event.target.value)} required>
                  <option value="all">Select a project</option>
                  {projects.map((project) => <option value={String(project.id)} key={project.id}>{project.title}</option>)}
                </select>
              </label>
              <label>TASK TITLE
                <input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} placeholder="Define a concrete engineering task" required />
              </label>
              <label>DESCRIPTION
                <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={3} placeholder="Acceptance criteria or useful context" />
              </label>
              <label>PRIORITY
                <select value={priority} onChange={(event) => setPriority(event.target.value)}>
                  <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option>
                </select>
              </label>
              <button className="primary wide" type="submit" disabled={busy || projectId === "all"}>{busy ? "SAVING..." : "CREATE TASK"}</button>
            </form>
          </section>

          <section className="panel">
            <div className="panel-head"><div><span className="panel-kicker">AUDIT TRAIL</span><h2>Recorded activity</h2></div><button className="text-btn" onClick={() => go("/projects")}>PROJECTS →</button></div>
            <div className="engineering-activity-list">
              {activity.slice(0, 8).map((item) => (
                <div className="engineering-activity" key={item.id}>
                  <span className="engineering-activity-dot" />
                  <div><strong>{item.verb}</strong><p>{item.message}</p><small>{item.actor_name || item.actor || "Workspace user"} · {item.created_at ? new Date(item.created_at).toLocaleString() : "Time unavailable"}</small></div>
                </div>
              ))}
              {!activity.length && <div className="empty">No recorded activity is available yet.</div>}
            </div>
          </section>
        </aside>
      </div>

      <section className="engineering-boundaries panel">
        <div><span className="panel-kicker">CONTROL & TRUST BOUNDARIES</span><h2>Capabilities not connected</h2></div>
        <ul>
          <li>Agent assignment, orchestration runs and live agent events</li>
          <li>Approval gates, checkpoints, rollback and recovery records</li>
          <li>Test-run evidence and independently verified completion</li>
          <li>WebSocket or event-stream synchronization (currently API refresh)</li>
        </ul>
        <p>These controls are intentionally not presented as operational until the backend exposes persisted APIs and verifiable execution evidence.</p>
      </section>
    </div>
  );
}
