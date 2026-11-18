import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../../services/api";

const LIFECYCLE = ["Think", "Plan", "Design", "Build", "Test", "Debug", "Repair"];
const TASK_STATES = [
  ["todo", "Planned"],
  ["in_progress", "In progress"],
  ["blocked", "Blocked"],
  ["done", "Completed"],
];

function listOf(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.results)) return value.results;
  return [];
}

async function apiJson(path, options) {
  const response = await apiFetch(path, options);
  if (response.status === 204) return null;
  return response.json();
}

function formatDate(value) {
  if (!value) return "No due date";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString();
}

function formatTimestamp(value) {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleString();
}

export default function EngineeringControlCenter({ go }) {
  const [projects, setProjects] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [activity, setActivity] = useState([]);
  const [workspaces, setWorkspaces] = useState([]);
  const [projectId, setProjectId] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [mode, setMode] = useState("manual");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);

  const [taskTitle, setTaskTitle] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const [priority, setPriority] = useState("medium");
  const [creatingTask, setCreatingTask] = useState(false);
  const [updatingTaskId, setUpdatingTaskId] = useState(null);

  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [dependencies, setDependencies] = useState([]);
  const [dependencyTarget, setDependencyTarget] = useState("");
  const [dependencyBusy, setDependencyBusy] = useState(false);

  const [workspaceId, setWorkspaceId] = useState("");
  const [command, setCommand] = useState("npm test");
  const [executing, setExecuting] = useState(false);
  const [execution, setExecution] = useState(null);
  const [executionError, setExecutionError] = useState("");

  const [prompt, setPrompt] = useState("");
  const [asking, setAsking] = useState(false);
  const [assistantReply, setAssistantReply] = useState(null);
  const [assistantError, setAssistantError] = useState("");

  const load = useCallback(async ({ quiet = false } = {}) => {
    if (quiet) setRefreshing(true);
    else {
      setLoading(true);
      setError("");
    }
    try {
      const [projectData, taskData, activityData, workspaceData] = await Promise.all([
        apiJson("/projects/"),
        apiJson("/tasks/"),
        apiJson("/activity/"),
        apiJson("/ide/workspaces/"),
      ]);
      const nextProjects = listOf(projectData);
      const nextTasks = listOf(taskData);
      const nextWorkspaces = listOf(workspaceData);
      setProjects(nextProjects);
      setTasks(nextTasks);
      setActivity(listOf(activityData));
      setWorkspaces(nextWorkspaces);
      setLastUpdated(new Date());
      setWorkspaceId((current) => current || (nextWorkspaces[0] ? String(nextWorkspaces[0].id) : ""));
      setSelectedTaskId((current) => current || (nextTasks[0] ? String(nextTasks[0].id) : ""));
    } catch (err) {
      setError(err.message || "Unable to load workspace data from the API.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(() => load({ quiet: true }), 20000);
    const onFocus = () => load({ quiet: true });
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
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

  const selectedTask = tasks.find((task) => String(task.id) === selectedTaskId);
  const selectedProject = projects.find((project) => String(project.id) === projectId);
  const selectedWorkspace = workspaces.find((workspace) => String(workspace.id) === workspaceId);

  const loadDependencies = useCallback(async (taskId) => {
    if (!taskId) {
      setDependencies([]);
      return;
    }
    try {
      const data = await apiJson(`/tasks/${taskId}/dependencies/`);
      setDependencies(listOf(data));
    } catch (err) {
      setError(err.message || "Unable to load task dependencies.");
    }
  }, []);

  useEffect(() => {
    loadDependencies(selectedTaskId);
  }, [selectedTaskId, loadDependencies]);

  const createTask = async (event) => {
    event.preventDefault();
    if (!taskTitle.trim() || projectId === "all") {
      setError(projectId === "all" ? "Select a project before creating a task." : "Task title is required.");
      return;
    }
    setCreatingTask(true);
    setError("");
    try {
      const created = await apiJson("/tasks/", {
        method: "POST",
        body: JSON.stringify({
          project: Number(projectId),
          title: taskTitle.trim(),
          description: taskDescription.trim(),
          priority,
          status: "todo",
        }),
      });
      setTaskTitle("");
      setTaskDescription("");
      if (created?.id) setSelectedTaskId(String(created.id));
      await load({ quiet: true });
    } catch (err) {
      setError(err.message || "Task could not be created.");
    } finally {
      setCreatingTask(false);
    }
  };

  const updateTask = async (task, nextStatus) => {
    if (task.status === nextStatus) return;
    setUpdatingTaskId(task.id);
    setError("");
    try {
      await apiJson(`/tasks/${task.id}/`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      await load({ quiet: true });
    } catch (err) {
      setError(err.message || "Task status could not be saved.");
    } finally {
      setUpdatingTaskId(null);
    }
  };

  const addDependency = async (event) => {
    event.preventDefault();
    if (!selectedTaskId || !dependencyTarget) return;
    setDependencyBusy(true);
    setError("");
    try {
      await apiJson(`/tasks/${selectedTaskId}/dependencies/`, {
        method: "POST",
        body: JSON.stringify({ depends_on: Number(dependencyTarget) }),
      });
      setDependencyTarget("");
      await loadDependencies(selectedTaskId);
    } catch (err) {
      setError(err.message || "Dependency could not be created.");
    } finally {
      setDependencyBusy(false);
    }
  };

  const removeDependency = async (dependencyId) => {
    setDependencyBusy(true);
    setError("");
    try {
      await apiJson(`/tasks/${selectedTaskId}/dependencies/`, {
        method: "DELETE",
        body: JSON.stringify({ dependency_id: dependencyId }),
      });
      await loadDependencies(selectedTaskId);
    } catch (err) {
      setError(err.message || "Dependency could not be removed.");
    } finally {
      setDependencyBusy(false);
    }
  };

  const runCommand = async (event) => {
    event.preventDefault();
    if (!workspaceId || !command.trim()) {
      setExecutionError("Choose a configured workspace and enter a command.");
      return;
    }
    setExecuting(true);
    setExecutionError("");
    setExecution(null);
    try {
      const result = await apiJson(`/ide/workspaces/${workspaceId}/execute/`, {
        method: "POST",
        body: JSON.stringify({ command: command.trim() }),
      });
      setExecution(result);
      await load({ quiet: true });
    } catch (err) {
      setExecutionError(err.message || "The runner could not execute this command.");
    } finally {
      setExecuting(false);
    }
  };

  const askIntelligence = async (event) => {
    event.preventDefault();
    if (!prompt.trim() || projectId === "all") {
      setAssistantError("Select a project and enter a question.");
      return;
    }
    setAsking(true);
    setAssistantError("");
    setAssistantReply(null);
    try {
      const result = await apiJson("/ai/chat/", {
        method: "POST",
        body: JSON.stringify({ project: Number(projectId), message: prompt.trim() }),
      });
      setAssistantReply(result?.message || null);
      if (!result?.message?.content) setAssistantError("The intelligence API returned no assistant message.");
    } catch (err) {
      setAssistantError(err.message || "Workspace intelligence is unavailable.");
    } finally {
      setAsking(false);
    }
  };

  const modeInfo = {
    manual: {
      title: "Manual Build",
      detail: "Tasks, dependencies and runner executions are connected to persisted backend records.",
      state: "connected",
    },
    agent: {
      title: "AI Agent Build",
      detail: "The current backend provides context-aware AI chat, but not autonomous agent planning, tool orchestration or verified multi-step runs. Agent execution is not enabled.",
      state: "unavailable",
    },
    hybrid: {
      title: "Hybrid Build",
      detail: "Human task control is available. Coordinated human/agent execution requires orchestration and approval APIs that are not currently exposed.",
      state: "unavailable",
    },
  }[mode];

  return (
    <div className="page engineering-page">
      <div className="hero-row engineering-hero">
        <div>
          <div className="eyebrow">DEVELOPER OS / ENGINEERING CONTROL</div>
          <h1>Engineering OS</h1>
          <p>Operate project work, dependencies, contextual intelligence and real runner executions.</p>
        </div>
        <div className="engineering-sync">
          <span className="engineering-live-dot" />
          API POLLING
          <small>{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Waiting for API"}</small>
          <button className="ghost" onClick={() => load()} type="button" disabled={loading || refreshing}>
            {refreshing ? "SYNCING..." : "REFRESH"}
          </button>
        </div>
      </div>

      {error && <div className="error" role="alert">{error}</div>}

      <section className="engineering-mode-grid" aria-label="Build modes">
        {[
          { id: "manual", name: "Manual Build", note: "Tasks + dependencies + runner", connected: true },
          { id: "agent", name: "AI Agent Build", note: "Orchestration API not available", connected: false },
          { id: "hybrid", name: "Hybrid Build", note: "Coordination API not available", connected: false },
        ].map((item) => (
          <button
            type="button"
            key={item.id}
            className={`engineering-mode ${mode === item.id ? "selected" : ""} ${!item.connected ? "unavailable" : ""}`}
            onClick={() => setMode(item.id)}
            aria-pressed={mode === item.id}
          >
            <span>{item.connected ? "BACKEND CONNECTED" : "NOT AVAILABLE"}</span>
            <strong>{item.name}</strong>
            <small>{item.note}</small>
          </button>
        ))}
      </section>

      <section className="engineering-stage-panel panel">
        <div className="panel-head">
          <div><span className="panel-kicker">ENGINEERING LIFECYCLE</span><h2>Think → Plan → Design → Build → Test → Debug → Repair</h2></div>
          <span className="engineering-source">Lifecycle map · execution evidence shown below</span>
        </div>
        <div className="engineering-stages">
          {LIFECYCLE.map((stage, index) => (
            <div className="engineering-stage" key={stage}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <b>{stage}</b>
            </div>
          ))}
        </div>
        <p className={modeInfo.state === "connected" ? "engineering-mode-note" : "engineering-mode-note warning"}>
          <strong>{modeInfo.title} · {modeInfo.state === "connected" ? "CONNECTED" : "UNAVAILABLE"}:</strong> {modeInfo.detail}
        </p>
      </section>

      <section className="engineering-metrics" aria-label="Persisted task totals">
        {[
          ["TASKS", counts.total],
          ["IN PROGRESS", counts.active],
          ["BLOCKED", counts.blocked],
          ["COMPLETED", counts.completed],
        ].map(([label, value]) => (
          <div className="stat-card" key={label}><span>{label}</span><strong>{value}</strong><small>Backend task records</small></div>
        ))}
      </section>

      <div className="engineering-work-grid">
        <section className="panel">
          <div className="panel-head">
            <div><span className="panel-kicker">PERSISTED WORK ITEMS</span><h2>Execution queue</h2></div>
            <span className="engineering-source">{loading ? "Loading…" : `${visibleTasks.length} shown`}</span>
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
                {TASK_STATES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
            </label>
          </div>
          <div className="engineering-task-list">
            {visibleTasks.map((task) => (
              <article className={`engineering-task ${selectedTaskId === String(task.id) ? "selected-task" : ""}`} key={task.id}>
                <button className="engineering-task-main" type="button" onClick={() => setSelectedTaskId(String(task.id))}>
                  <span className={`engineering-task-state state-${task.status}`}>{TASK_STATES.find(([value]) => value === task.status)?.[1] || task.status}</span>
                  <strong>{task.title}</strong>
                  <small>{projects.find((project) => String(project.id) === String(task.project))?.title || `Project #${task.project ?? "—"}`} · {task.priority} · Due {formatDate(task.due_date)}</small>
                  {task.description && <p>{task.description}</p>}
                </button>
                <label className="engineering-status-control">
                  <span className="sr-only">Update status for {task.title}</span>
                  <select value={task.status} disabled={updatingTaskId === task.id} onChange={(event) => updateTask(task, event.target.value)}>
                    {TASK_STATES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                </label>
              </article>
            ))}
            {!loading && !visibleTasks.length && <div className="empty">{tasks.length ? "No tasks match these filters." : "No persisted tasks found. Create a task for a project."}</div>}
          </div>
        </section>

        <aside className="engineering-side">
          <section className="panel">
            <span className="panel-kicker">TASK INTAKE</span>
            <h2>Create work item</h2>
            <p className="engineering-muted">Creates a task under the selected project using the existing authenticated API.</p>
            <form className="engineering-create-form" onSubmit={createTask}>
              <label>PROJECT
                <select value={projectId} onChange={(event) => setProjectId(event.target.value)} required>
                  <option value="all">Select a project</option>
                  {projects.map((project) => <option value={String(project.id)} key={project.id}>{project.title}</option>)}
                </select>
              </label>
              <label>TASK TITLE
                <input value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} maxLength={200} placeholder="Define a concrete engineering task" required />
              </label>
              <label>DESCRIPTION
                <textarea value={taskDescription} onChange={(event) => setTaskDescription(event.target.value)} rows={3} placeholder="Acceptance criteria and context" />
              </label>
              <label>PRIORITY
                <select value={priority} onChange={(event) => setPriority(event.target.value)}>
                  <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option>
                </select>
              </label>
              <button className="primary wide" type="submit" disabled={creatingTask || projectId === "all"}>{creatingTask ? "SAVING..." : "CREATE TASK"}</button>
            </form>
          </section>

          <section className="panel">
            <div className="panel-head"><div><span className="panel-kicker">DEPENDENCY GRAPH</span><h2>Task prerequisites</h2></div></div>
            <p className="engineering-muted">Dependencies are saved through the project task dependency API.</p>
            <label className="engineering-create-form">SELECT TASK
              <select value={selectedTaskId} onChange={(event) => setSelectedTaskId(event.target.value)}>
                <option value="">Choose a task</option>
                {tasks.map((task) => <option value={String(task.id)} key={task.id}>{task.title}</option>)}
              </select>
            </label>
            {selectedTask && <form className="engineering-dependency-form" onSubmit={addDependency}>
              <select aria-label="Task that must be completed first" value={dependencyTarget} onChange={(event) => setDependencyTarget(event.target.value)}>
                <option value="">Add prerequisite…</option>
                {tasks.filter((task) => task.project === selectedTask.project && task.id !== selectedTask.id && !dependencies.some((dep) => dep.depends_on === task.id)).map((task) => <option value={String(task.id)} key={task.id}>{task.title}</option>)}
              </select>
              <button className="primary" type="submit" disabled={dependencyBusy || !dependencyTarget}>ADD</button>
            </form>}
            <div className="engineering-dependency-list">
              {dependencies.map((dependency) => {
                const prerequisite = tasks.find((task) => task.id === dependency.depends_on);
                return <div className="engineering-dependency" key={dependency.id}>
                  <span>{prerequisite?.title || `Task #${dependency.depends_on}`}</span>
                  <button type="button" className="text-btn" disabled={dependencyBusy} onClick={() => removeDependency(dependency.id)}>REMOVE</button>
                </div>;
              })}
              {!dependencies.length && <div className="empty">No prerequisites recorded for this task.</div>}
            </div>
          </section>
        </aside>
      </div>

      <section className="panel engineering-runner-panel">
        <div className="panel-head">
          <div><span className="panel-kicker">BUILD / TEST / DEBUG</span><h2>Workspace runner</h2></div>
          <span className="engineering-source">Authenticated backend → configured runner</span>
        </div>
        <p className="engineering-muted">Commands execute only in an existing workspace through the configured IDE runner. Results below are the runner's actual response, not simulated progress.</p>
        <form className="engineering-runner-form" onSubmit={runCommand}>
          <label>WORKSPACE
            <select value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)}>
              <option value="">Select a workspace</option>
              {workspaces.map((workspace) => <option value={String(workspace.id)} key={workspace.id}>{workspace.name} · #{workspace.id}</option>)}
            </select>
          </label>
          <label>COMMAND
            <input value={command} onChange={(event) => setCommand(event.target.value)} maxLength={2000} placeholder="npm test / npm run build / python manage.py test" />
          </label>
          <button className="primary" type="submit" disabled={executing || !workspaceId || !command.trim()}>{executing ? "RUNNING..." : "EXECUTE"}</button>
        </form>
        {!workspaces.length && !loading && <div className="empty">No IDE workspace exists for this account. Create one in Web IDE before running commands.</div>}
        {selectedWorkspace && <p className="engineering-muted">Selected workspace: {selectedWorkspace.name} · Last modified {formatTimestamp(selectedWorkspace.updated_at)}</p>}
        {executionError && <div className="error" role="alert">{executionError}</div>}
        {execution && <div className="engineering-execution">
          <div className="engineering-execution-meta">
            <strong>Execution #{execution.id}</strong>
            <span className={execution.status === "success" ? "execution-success" : "execution-failed"}>{execution.status?.toUpperCase()}</span>
            <small>Exit code: {execution.exit_code ?? "not returned"} · Duration: {execution.duration_ms ?? "—"} ms</small>
          </div>
          {execution.stdout && <div><b>STDOUT</b><pre>{execution.stdout}</pre></div>}
          {execution.stderr && <div><b>STDERR</b><pre>{execution.stderr}</pre></div>}
          {!execution.stdout && !execution.stderr && <p className="engineering-muted">Runner returned no output.</p>}
          <small>Runner-reported process result. A zero exit code does not independently prove application correctness.</small>
        </div>}
      </section>

      <section className="engineering-intelligence panel">
        <div><span className="panel-kicker">PROJECT INTELLIGENCE</span><h2>Context-aware engineering assistant</h2></div>
        <p className="engineering-muted">Uses the existing AI chat endpoint with the selected project's saved workspace context. Provider-backed generation depends on server configuration.</p>
        <form className="engineering-intelligence-form" onSubmit={askIntelligence}>
          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={3} placeholder="Ask about architecture, task sequencing, risks, debugging or project context…" />
          <button className="primary" type="submit" disabled={asking || projectId === "all" || !prompt.trim()}>{asking ? "ANALYZING..." : "ASK PROJECT INTELLIGENCE"}</button>
        </form>
        {assistantError && <div className="error" role="alert">{assistantError}</div>}
        {assistantReply?.content && <article className="engineering-assistant-reply"><span className="panel-kicker">SAVED ASSISTANT RESPONSE · {formatTimestamp(assistantReply.created_at)}</span><p>{assistantReply.content}</p></article>}
      </section>

      <section className="panel">
        <div className="panel-head"><div><span className="panel-kicker">AUDIT TRAIL</span><h2>Recorded workspace activity</h2></div><button className="text-btn" onClick={() => go("/projects")}>PROJECTS →</button></div>
        <div className="engineering-activity-list">
          {activity.slice(0, 10).map((item) => (
            <div className="engineering-activity" key={item.id}>
              <span className="engineering-activity-dot" />
              <div><strong>{item.verb}</strong><p>{item.message}</p><small>User ID: {item.actor ?? "system"} · {formatTimestamp(item.created_at)}</small></div>
            </div>
          ))}
          {!activity.length && <div className="empty">No recorded activity is available.</div>}
        </div>
      </section>

      <section className="engineering-boundaries panel">
        <div><span className="panel-kicker">EXECUTION TRUST BOUNDARIES</span><h2>Not represented as available</h2></div>
        <ul>
          <li>Autonomous agent assignment and multi-agent orchestration</li>
          <li>Human approval gates, checkpoints and rollback recovery</li>
          <li>Independent test verification and signed completion evidence</li>
          <li>WebSocket/SSE events; current synchronization is API polling</li>
        </ul>
        <p>Agent Build and Hybrid Build remain unavailable until real backend contracts, persisted run state and verification evidence exist.</p>
      </section>
    </div>
  );
}
