import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "./services/api";
import "./ProWorkspace.css";
import ProIDE from "./ProIDE";

const emptyProject = { title: "", description: "", category: "General", status: "Planning", priority: "medium", link: "", deadline: "", tags: [] };
const emptyTask = { title: "", description: "", priority: "medium", status: "todo", due_date: "" };
const statusLabel = { todo: "To do", in_progress: "In progress", done: "Done", blocked: "Blocked" };
const priorityLabel = { low: "Low", medium: "Medium", high: "High", urgent: "Urgent" };

function Stat({ label, value, hint, tone = "cyan" }) {
  return <article className={`pro-stat ${tone}`}><div className="stat-icon">{tone === "green" ? "✓" : tone === "violet" ? "✦" : tone === "amber" ? "◷" : "⌁"}</div><div><span>{label}</span><strong>{value}</strong><small>{hint}</small></div></article>;
}

function EmptyState({ title, text, action, onAction }) {
  return <div className="pro-empty"><div className="empty-orb">+</div><strong>{title}</strong><p>{text}</p>{action && <button className="pro-button primary" onClick={onAction}>{action}</button>}</div>;
}

function formatDate(value) {
  if (!value) return "—";
  try { return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(value)); } catch { return value; }
}

function relativeTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "recently";
  const minutes = Math.max(1, Math.floor((Date.now() - date.getTime()) / 60000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function ProWorkspace({ profile, onLogout, onNavigate }) {
  const [projects, setProjects] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [snippets, setSnippets] = useState([]);
  const [notes, setNotes] = useState([]);
  const [activities, setActivities] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [projectForm, setProjectForm] = useState(emptyProject);
  const [taskForm, setTaskForm] = useState(emptyTask);
  const [noteForm, setNoteForm] = useState({ title: "", content: "" });
  const [editor, setEditor] = useState({ title: "main.py", language: "py", code: "# Start building\n\n" });
  const [tab, setTab] = useState("overview");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [mobileNav, setMobileNav] = useState(false);
  const [health, setHealth] = useState("checking");

  const selectedProject = projects.find((p) => p.id === selectedId) || projects[0] || null;
  const projectTasks = useMemo(() => tasks.filter((t) => t.project === selectedProject?.id), [tasks, selectedProject]);
  const projectNotes = useMemo(() => notes.filter((n) => n.project === selectedProject?.id), [notes, selectedProject]);
  const visibleProjects = projects.filter((p) => `${p.title} ${p.description} ${p.category}`.toLowerCase().includes(query.toLowerCase()));
  const done = tasks.filter((t) => t.status === "done").length;
  const active = tasks.filter((t) => t.status !== "done").length;
  const blocked = tasks.filter((t) => t.status === "blocked").length;
  const urgent = tasks.filter((t) => t.priority === "urgent" && t.status !== "done").length;
  const completion = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
  const projectProgress = selectedProject?.progress ?? 0;

  const load = useCallback(async () => {
    setBusy(true);
    try {
      const [p, t, s, n, a] = await Promise.all([
        apiFetch("/projects/"), apiFetch("/tasks/"), apiFetch("/snippets/"), apiFetch("/notes/"), apiFetch("/activity/"),
      ]);
      const [projectsData, tasksData, snippetsData, notesData, activityData] = await Promise.all([p.json(), t.json(), s.json(), n.json(), a.json()]);
      setProjects(Array.isArray(projectsData) ? projectsData : []);
      setTasks(Array.isArray(tasksData) ? tasksData : []);
      setSnippets(Array.isArray(snippetsData) ? snippetsData : []);
      setNotes(Array.isArray(notesData) ? notesData : []);
      setActivities(Array.isArray(activityData) ? activityData : []);
      if (!selectedId && projectsData?.[0]) setSelectedId(projectsData[0].id);
      if (selectedId && !projectsData.some((p) => p.id === selectedId)) setSelectedId(projectsData?.[0]?.id || null);
    } catch (e) { setMessage(e.message || "Unable to sync workspace."); }
    finally { setBusy(false); }
  }, [selectedId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { let live = true; apiFetch("/health/ready/").then(r => r.json()).then(d => live && setHealth(d.status === "ready" ? "operational" : "degraded")).catch(() => live && setHealth("offline")); return () => { live = false; }; }, []);
  useEffect(() => { if (message) { const t = setTimeout(() => setMessage(""), 4200); return () => clearTimeout(t); } }, [message]);

  async function createProject(e) {
    e.preventDefault();
    if (!projectForm.title.trim()) return;
    setBusy(true);
    try {
      const payload = { ...projectForm, deadline: projectForm.deadline || null };
      const response = await apiFetch("/projects/", { method: "POST", body: JSON.stringify(payload) });
      const project = await response.json();
      setProjects((x) => [project, ...x]); setSelectedId(project.id); setProjectForm(emptyProject); setTab("overview"); setMessage("Project created");
    } catch (e) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function createTask(e) {
    e.preventDefault();
    if (!selectedProject || !taskForm.title.trim()) return;
    setBusy(true);
    try {
      const response = await apiFetch("/tasks/", { method: "POST", body: JSON.stringify({ ...taskForm, project: selectedProject.id, due_date: taskForm.due_date || null, tags: [] }) });
      const task = await response.json(); setTasks((x) => [task, ...x]); setTaskForm(emptyTask); setMessage("Task added"); await load();
    } catch (e) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function updateTask(task, patch) {
    try {
      const response = await apiFetch(`/tasks/${task.id}/`, { method: "PATCH", body: JSON.stringify(patch) });
      const updated = await response.json(); setTasks((x) => x.map((item) => item.id === updated.id ? updated : item)); await load();
    } catch (e) { setMessage(e.message); }
  }

  async function deleteTask(task) {
    if (!window.confirm(`Delete “${task.title}”?`)) return;
    try { await apiFetch(`/tasks/${task.id}/`, { method: "DELETE" }); setTasks((x) => x.filter((item) => item.id !== task.id)); await load(); setMessage("Task deleted"); } catch (e) { setMessage(e.message); }
  }

  async function saveProject() {
    if (!selectedProject) return;
    try {
      const response = await apiFetch(`/projects/${selectedProject.id}/`, { method: "PATCH", body: JSON.stringify({ title: selectedProject.title, description: selectedProject.description, category: selectedProject.category, status: selectedProject.status, priority: selectedProject.priority, link: selectedProject.link || "", deadline: selectedProject.deadline || null, tags: selectedProject.tags || [] }) });
      const updated = await response.json(); setProjects((x) => x.map((p) => p.id === updated.id ? updated : p)); setMessage("Project saved"); await load();
    } catch (e) { setMessage(e.message); }
  }

  async function deleteProject() {
    if (!selectedProject || !window.confirm(`Delete “${selectedProject.title}” and its tasks?`)) return;
    try { await apiFetch(`/projects/${selectedProject.id}/`, { method: "DELETE" }); setProjects((x) => x.filter((p) => p.id !== selectedProject.id)); setTasks((x) => x.filter((t) => t.project !== selectedProject.id)); setSelectedId(null); setMessage("Project deleted"); await load(); } catch (e) { setMessage(e.message); }
  }

  async function createNote(e) {
    e.preventDefault();
    if (!selectedProject || !noteForm.content.trim()) return;
    try {
      const response = await apiFetch("/notes/", { method: "POST", body: JSON.stringify({ ...noteForm, project: selectedProject.id }) });
      const note = await response.json(); setNotes((x) => [note, ...x]); setNoteForm({ title: "", content: "" }); setMessage("Note saved"); await load();
    } catch (e) { setMessage(e.message); }
  }

  async function deleteNote(note) {
    if (!window.confirm("Delete this note?")) return;
    try { await apiFetch(`/notes/${note.id}/`, { method: "DELETE" }); setNotes((x) => x.filter((n) => n.id !== note.id)); setMessage("Note deleted"); } catch (e) { setMessage(e.message); }
  }

  async function connectGitHub() {
    try { const response = await apiFetch("/github/authorize/"); const data = await response.json(); if (data.authorization_url) window.location.href = data.authorization_url; else setMessage(data.error || "GitHub integration is not configured."); } catch (e) { setMessage(e.message); }
  }

  async function saveSnippet() {
    if (!editor.title.trim() || !editor.code.trim()) return;
    try { const response = await apiFetch("/snippets/", { method: "POST", body: JSON.stringify({ ...editor, project: selectedProject?.id || null }) }); const saved = await response.json(); setSnippets((x) => [saved, ...x]); setMessage("Snippet saved"); } catch (e) { setMessage(e.message); }
  }

  const insight = blocked ? `${blocked} blocked task${blocked > 1 ? "s" : ""} need attention.` : urgent ? `${urgent} urgent item${urgent > 1 ? "s" : ""} should be cleared next.` : completion >= 70 ? "Execution is moving well. Protect the current focus." : active ? "Create a small next milestone and keep the board moving." : "Create your first task to start measuring delivery.";

  return <div className="pro-shell">
    <aside className={`pro-sidebar ${mobileNav ? "open" : ""}`}>
      <div className="pro-logo"><div className="pro-logo-mark">D</div><div><b>Developer<span>OS</span></b><small>Product engineering workspace</small></div></div>
      <div className="pro-nav-label">WORKSPACE</div>
      <button className={`pro-nav ${tab === "overview" ? "active" : ""}`} onClick={() => { setTab("overview"); setMobileNav(false); }}>⌂ <span>Command center</span></button>
      <button className={`pro-nav ${tab === "tasks" ? "active" : ""}`} onClick={() => { setTab("tasks"); setMobileNav(false); }}>✓ <span>Tasks</span><em>{active}</em></button>
      <button className={`pro-nav ${tab === "notes" ? "active" : ""}`} onClick={() => { setTab("notes"); setMobileNav(false); }}>✎ <span>Notes</span><em>{notes.length}</em></button>
      <button className={`pro-nav ${tab === "editor" ? "active" : ""}`} onClick={() => { setTab("editor"); setMobileNav(false); }}>⌘ <span>Code Lab</span></button>
      <button className="pro-nav" onClick={() => onNavigate?.("advanced")}>◈ <span>Analytics</span></button>
      <button className="pro-nav" onClick={() => onNavigate?.("ai")}>✦ <span>AI assistant</span></button>
      <button className="pro-nav" onClick={() => onNavigate?.("collaboration")}>◎ <span>Collaboration</span></button>
      <button className="pro-nav" onClick={() => onNavigate?.("github")}>◉ <span>GitHub</span></button>
      <button className="pro-nav" onClick={() => onNavigate?.("resources")}>◇ <span>Resources</span></button>
      <div className="pro-nav-label">SYSTEM</div>
      <button className="pro-nav" onClick={() => onNavigate?.("profile")}>◎ <span>Profile</span></button>
      <button className="pro-nav" onClick={onLogout}>↪ <span>Sign out</span></button>
      <div className="pro-sidebar-bottom"><div className="pro-status-dot"/><span>API connected · secure session</span></div>
    </aside>

    <main className="pro-main">
      <header className="pro-topbar">
        <button className="mobile-menu" onClick={() => setMobileNav(!mobileNav)} aria-label="Toggle navigation">☰</button>
        <div className="pro-breadcrumb"><span>Developer OS</span><i>/</i><strong>{selectedProject?.title || "Command center"}</strong></div>
        <div className="pro-top-actions"><div className="pro-search">⌕<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search projects…" /></div><div className="pro-avatar" title={profile?.username || "Developer"}>{(profile?.username || "D").slice(0,1).toUpperCase()}</div><button className="pro-logout" onClick={onLogout}>Sign out</button></div>
      </header>

      <section className="pro-hero">
        <div><span className="pro-kicker">DEVELOPER OPERATING SYSTEM</span><h1>Build. Ship. <span>Repeat.</span></h1><p>A focused command center for projects, execution, reusable code and delivery context — backed by your real workspace data.</p></div>
        <div className="pro-hero-actions"><button className="pro-button primary" onClick={() => document.getElementById("new-project")?.scrollIntoView({ behavior: "smooth" })}>＋ New project</button><button className="pro-button ghost" onClick={load} disabled={busy}>↻ {busy ? "Syncing" : "Sync"}</button></div>
      </section>

      {message && <div className="pro-toast">{message}<button onClick={() => setMessage("")}>×</button></div>}

      <section className="pro-stats"><Stat label="Projects" value={projects.length} hint="Workspace scope"/><Stat label="Active tasks" value={active} hint={`${urgent} urgent`} tone="amber"/><Stat label="Completion" value={`${completion}%`} hint={`${done} completed`} tone="green"/><Stat label="Snippets" value={snippets.length} hint="Reusable knowledge" tone="violet"/></section>

      <div className="pro-layout">
        <section className="pro-content">
          <div className="pro-section-head"><div><span className="pro-kicker">PROJECT SPACE</span><h2>{selectedProject?.title || "Your projects"}</h2></div><div className="pro-tabs">{[["overview","Overview"],["tasks","Tasks"],["notes","Notes"],["editor","Code Lab"]].map(([key,label]) => <button key={key} className={tab === key ? "selected" : ""} onClick={() => setTab(key)}>{label}{key === "tasks" && active ? <b>{active}</b> : null}</button>)}</div></div>

          {!selectedProject && <EmptyState title="Your command center is ready" text="Create your first project and DeveloperOS will turn its tasks, notes and delivery progress into a live workspace." action="Create project" onAction={() => document.getElementById("new-project")?.scrollIntoView({ behavior: "smooth" })}/>} 

          {selectedProject && tab === "overview" && <div className="pro-overview-grid">
            <div className="pro-panel pro-progress"><div className="pro-panel-title"><span>Delivery progress</span><b>{projectProgress}%</b></div><div className="pro-progress-track"><i style={{ width: `${projectProgress}%` }}/></div><div className="pro-progress-meta"><span>{projectTasks.filter(t => t.status === "done").length} of {projectTasks.length} tasks complete</span><span>{selectedProject.status}</span></div><div className="progress-grid"><div><small>Priority</small><strong>{priorityLabel[selectedProject.priority] || "Medium"}</strong></div><div><small>Deadline</small><strong>{formatDate(selectedProject.deadline)}</strong></div><div><small>Tasks</small><strong>{projectTasks.length}</strong></div></div></div>
            <div className="pro-panel"><div className="pro-panel-title"><span>Project context</span><b>{selectedProject.category}</b></div><input className="pro-inline-input" value={selectedProject.title} onChange={e => setProjects(x => x.map(p => p.id === selectedProject.id ? { ...p, title: e.target.value } : p))}/><textarea className="pro-inline-textarea" value={selectedProject.description || ""} onChange={e => setProjects(x => x.map(p => p.id === selectedProject.id ? { ...p, description: e.target.value } : p))}/><div className="context-actions"><button onClick={saveProject}>Save changes</button><button onClick={connectGitHub}>Connect GitHub</button><button className="danger" onClick={deleteProject}>Delete</button></div></div>
            <div className="pro-panel full"><div className="pro-panel-title"><span>Execution board</span><b>{projectTasks.length} items</b></div><div className="pro-mini-board">{Object.entries(statusLabel).slice(0,3).map(([s,label]) => <div key={s}><h4>{label}</h4>{projectTasks.filter(t => t.status === s).slice(0,5).map(t => <button className="pro-mini-task" key={t.id} onClick={() => setTab("tasks")}><span className={`priority ${t.priority}`}/><strong>{t.title}</strong><small>{priorityLabel[t.priority]} · {t.due_date ? formatDate(t.due_date) : "No due date"}</small></button>)}{projectTasks.filter(t => t.status === s).length === 0 && <small className="muted">Nothing here yet</small>}</div>)}</div></div>
            <div className="pro-panel full analytics-panel"><div className="pro-panel-title"><span>Workspace intelligence</span><b>LIVE FROM YOUR DATA</b></div><div className="insight-row"><div className="insight-main"><span className="insight-icon">✦</span><div><strong>Focus signal</strong><p>{insight}</p></div></div><div className="metric"><small>Blocked</small><strong>{blocked}</strong></div><div className="metric"><small>Urgent</small><strong>{urgent}</strong></div><div className="metric"><small>Notes</small><strong>{projectNotes.length}</strong></div></div></div>
            <div className="pro-panel full"><div className="pro-panel-title"><span>Recent activity</span><button className="text-link" onClick={() => setTab("activity")}>View all</button></div>{activities.slice(0,5).length ? <div className="activity-list">{activities.slice(0,5).map(a => <div className="activity-row" key={a.id}><span className="activity-dot"/><div><strong>{a.verb}</strong><p>{a.message}</p></div><time>{relativeTime(a.created_at)}</time></div>)}</div> : <small className="muted">Your workspace history will appear here as you work.</small>}</div>
          </div>}

          {selectedProject && tab === "tasks" && <div className="pro-panel full"><div className="pro-panel-title"><span>Tasks</span><b>{projectTasks.length} items</b></div><form className="task-create" onSubmit={createTask}><input value={taskForm.title} onChange={e => setTaskForm({...taskForm,title:e.target.value})} placeholder="What needs to ship?"/><select value={taskForm.priority} onChange={e => setTaskForm({...taskForm,priority:e.target.value})}>{Object.entries(priorityLabel).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select><input type="date" value={taskForm.due_date} onChange={e => setTaskForm({...taskForm,due_date:e.target.value})}/><button className="pro-button primary" disabled={busy}>Add task</button></form><div className="task-list">{projectTasks.map(t => <div className="task-row" key={t.id}><button className={`check ${t.status === "done" ? "done" : ""}`} onClick={() => updateTask(t,{status:t.status === "done" ? "todo" : "done"})}>{t.status === "done" ? "✓" : ""}</button><div className="task-main"><strong>{t.title}</strong><small>{t.description || "No description"}{t.due_date ? ` · due ${formatDate(t.due_date)}` : ""}</small></div><select value={t.status} onChange={e => updateTask(t,{status:e.target.value})}>{Object.entries(statusLabel).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select><span className={`priority-pill ${t.priority}`}>{priorityLabel[t.priority]}</span><button className="delete" onClick={() => deleteTask(t)}>×</button></div>)}{projectTasks.length === 0 && <EmptyState title="No tasks yet" text="Turn the project brief into a few small deliverables."/>}</div></div>}

          {selectedProject && tab === "notes" && <div className="notes-layout"><div className="pro-panel"><div className="pro-panel-title"><span>New note</span><b>PROJECT MEMORY</b></div><form className="note-form" onSubmit={createNote}><input value={noteForm.title} onChange={e => setNoteForm({...noteForm,title:e.target.value})} placeholder="Note title"/><textarea value={noteForm.content} onChange={e => setNoteForm({...noteForm,content:e.target.value})} placeholder="Capture a decision, API detail, release note or useful context…"/><button className="pro-button primary">Save note</button></form></div><div className="pro-panel"><div className="pro-panel-title"><span>Project notes</span><b>{projectNotes.length}</b></div><div className="notes-list">{projectNotes.map(n => <article className="note-card" key={n.id}><div><strong>{n.title || "Untitled note"}</strong><small>{relativeTime(n.updated_at)}</small></div><p>{n.content}</p><button onClick={() => deleteNote(n)}>Delete</button></article>)}{projectNotes.length === 0 && <small className="muted">No notes yet. Your best decisions belong here.</small>}</div></div></div>}

          {tab === "activity" && <div className="pro-panel full"><div className="pro-panel-title"><span>Activity history</span><b>{activities.length}</b></div><div className="activity-list">{activities.map(a => <div className="activity-row" key={a.id}><span className="activity-dot"/><div><strong>{a.verb}</strong><p>{a.message}</p></div><time>{relativeTime(a.created_at)}</time></div>)}{activities.length === 0 && <small className="muted">No activity yet.</small>}</div></div>}

          {selectedProject && tab === "editor" && <ProIDE projectId={selectedProject.id} message={setMessage} />}</section>

        <aside className="pro-right">
          <div className="pro-panel project-list" id="new-project"><div className="pro-panel-title"><span>Projects</span><b>{visibleProjects.length}</b></div><form className="project-create" onSubmit={createProject}><input required placeholder="New project name" value={projectForm.title} onChange={e => setProjectForm({...projectForm,title:e.target.value})}/><div className="form-row"><select value={projectForm.category} onChange={e => setProjectForm({...projectForm,category:e.target.value})}>{["General","Frontend","Backend","AI","DevOps","Design","Productivity"].map(x => <option key={x}>{x}</option>)}</select><select value={projectForm.priority} onChange={e => setProjectForm({...projectForm,priority:e.target.value})}>{Object.entries(priorityLabel).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select></div><textarea placeholder="One-line project brief" value={projectForm.description} onChange={e => setProjectForm({...projectForm,description:e.target.value})}/><input type="date" value={projectForm.deadline} onChange={e => setProjectForm({...projectForm,deadline:e.target.value})}/><button className="pro-button primary full" disabled={busy}>Create project</button></form><div className="project-list-items">{visibleProjects.map(p => <button key={p.id} className={`project-item ${selectedProject?.id === p.id ? "active" : ""}`} onClick={() => { setSelectedId(p.id); setTab("overview"); }}><div className="project-icon">{p.title.slice(0,1).toUpperCase()}</div><div><strong>{p.title}</strong><small>{p.category} · {p.progress}%</small></div><span>›</span></button>)}{visibleProjects.length === 0 && <div className="muted empty">No projects match your search.</div>}</div></div>
          <div className="pro-panel next-panel"><div className="pro-panel-title"><span>Next actions</span><b>FOCUS</b></div><button className="next-item" onClick={() => setTab("tasks")}><span>01</span><div><strong>Finish active tasks</strong><small>{active} items waiting</small></div></button><button className="next-item" onClick={() => setTab("notes")}><span>02</span><div><strong>Capture project context</strong><small>{notes.length} notes saved</small></div></button><button className="next-item" onClick={connectGitHub}><span>03</span><div><strong>Connect GitHub</strong><small>Sync repositories & activity</small></div></button></div>
          <div className="pro-panel health-panel"><div className="pro-panel-title"><span>System health</span><b>LIVE</b></div><div className="health-line"><span><i className={health} />API</span><strong>{health === "checking" ? "Checking" : health[0].toUpperCase() + health.slice(1)}</strong></div><div className="health-line"><span><i className="operational"/>Session</span><strong>Secure</strong></div><div className="health-line"><span><i className="operational"/>Workspace</span><strong>{projects.length ? "Active" : "Ready"}</strong></div></div>
        </aside>
      </div>
    </main>
  </div>;
}
