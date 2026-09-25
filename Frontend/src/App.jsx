import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import { API_URL, apiFetch, clearAuth, getAccessToken, revokeRefreshToken } from "./services/api";

const nav = [
  ["dashboard", "⌂", "Command Center"],
  ["projects", "◈", "Projects"],
  ["ide", "⌘", "Web IDE"],
  ["ai", "✦", "Intelligence"],
  ["search", "⌕", "Universal Search"],
  ["team", "◎", "Team & Collab"],
  ["billing", "◇", "SaaS / Billing"],
  ["settings", "⚙", "Settings"],
];

function useRoute() {
  const [path, setPath] = useState(window.location.pathname || "/");
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname || "/");
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return [path, (next) => {
    window.history.pushState({}, "", next);
    setPath(next);
  }];
}

async function login(username, password) {
  const r = await fetch(`${API_URL}/token/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Invalid credentials.");
  sessionStorage.setItem("access", data.access);
  sessionStorage.setItem("refresh", data.refresh);
}

async function register(payload) {
  const r = await fetch(`${API_URL}/register/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "Registration failed.");
  await login(payload.username, payload.password);
}

function Shell({ user, onLogout, children, go, current }) {
  const [search, setSearch] = useState("");
  const [notifications, setNotifications] = useState({ unread: 0, items: [] });
  const [openNotif, setOpenNotif] = useState(false);

  useEffect(() => {
    let active = true;
    apiFetch("/notifications/").then(r => r.json()).then(d => active && setNotifications(d)).catch(() => {});
    return () => { active = false; };
  }, []);

  const runSearch = (e) => {
    if (e.key === "Enter" && search.trim()) {
      go(`/search?q=${encodeURIComponent(search.trim())}`);
      setSearch("");
    }
  };

  return (
    <div className="os-shell">
      <aside className="os-rail">
        <button className="brand" onClick={() => go("/")} title="Developer OS">
          <span className="brand-mark">D</span><span className="brand-text">DEVELOPER<span>OS</span></span>
        </button>
        <div className="rail-section">WORKSPACE</div>
        {nav.slice(0, 6).map(([id, icon, label]) => (
          <button key={id} className={`rail-item ${current === id ? "active" : ""}`} onClick={() => go(id === "dashboard" ? "/" : `/${id}`)}>
            <span>{icon}</span><em>{label}</em>
          </button>
        ))}
        <div className="rail-section">SYSTEM</div>
        {nav.slice(6).map(([id, icon, label]) => (
          <button key={id} className={`rail-item ${current === id ? "active" : ""}`} onClick={() => go(`/${id}`)}>
            <span>{icon}</span><em>{label}</em>
          </button>
        ))}
        <div className="rail-spacer" />
        <div className="status-chip"><i /> SYSTEM ONLINE</div>
        <button className="profile-mini" onClick={() => go("/settings")}>
          <span className="avatar">{(user.username || "D")[0].toUpperCase()}</span>
          <span><b>{user.username}</b><small>{user.email || "developer"}</small></span>
        </button>
      </aside>

      <main className="os-main">
        <header className="topbar">
          <div className="crumb"><span>DEVELOPER OS</span><b>/</b><strong>{current === "dashboard" ? "COMMAND CENTER" : current.toUpperCase()}</strong></div>
          <div className="top-actions">
            <div className="global-search">
              <span>⌕</span><input value={search} onChange={e => setSearch(e.target.value)} onKeyDown={runSearch} placeholder="Search everything  /  Ctrl K" />
            </div>
            <button className="icon-btn" onClick={() => setOpenNotif(v => !v)}>◌<sup>{notifications.unread || ""}</sup></button>
            <button className="icon-btn" onClick={() => go("/ide")}>⌘</button>
            <button className="logout-btn" onClick={() => { revokeRefreshToken(); clearAuth(); onLogout(); }}>EXIT</button>
          </div>
          {openNotif && <div className="notif-pop">
            <div className="pop-head"><b>Notifications</b><button onClick={() => apiFetch("/notifications/", {method:"PATCH",body:JSON.stringify({})}).then(() => setNotifications(n => ({...n, unread:0})))}>Mark read</button></div>
            {(notifications.items || []).slice(0, 8).map(n => <div className="notif" key={n.id}><b>{n.title}</b><span>{n.body}</span></div>)}
            {!notifications.items?.length && <div className="empty">No notifications.</div>}
          </div>}
        </header>
        <div className="os-content">{children}</div>
      </main>
    </div>
  );
}

function Auth({ onReady }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username:"", password:"", email:"", first_name:"", last_name:"" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      if (mode === "login") await login(form.username, form.password);
      else await register(form);
      onReady();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };

  return <div className="auth-screen">
    <div className="auth-grid" />
    <div className="auth-card">
      <div className="auth-logo"><span>D</span><div>DEVELOPER OS<small>THE OPERATING SYSTEM FOR DEVELOPERS</small></div></div>
      <div className="auth-copy"><span>BOOT SEQUENCE</span><h1>{mode === "login" ? "Enter the command center." : "Initialize your workspace."}</h1><p>Projects, intelligence, code, collaboration and delivery in one developer control plane.</p></div>
      <form onSubmit={submit}>
        {mode === "register" && <div className="two"><input placeholder="First name" value={form.first_name} onChange={e=>setForm({...form,first_name:e.target.value})}/><input placeholder="Last name" value={form.last_name} onChange={e=>setForm({...form,last_name:e.target.value})}/></div>}
        <input required placeholder="Username" value={form.username} onChange={e=>setForm({...form,username:e.target.value})}/>
        {mode === "register" && <input required type="email" placeholder="Email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})}/>}
        <input required type="password" placeholder="Password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/>
        {error && <div className="error">{error}</div>}
        <button className="primary wide" disabled={busy}>{busy ? "AUTHENTICATING..." : mode === "login" ? "ACCESS COMMAND CENTER →" : "CREATE DEVELOPER ID →"}</button>
      </form>
      <button className="switch" onClick={() => {setMode(mode==="login"?"register":"login");setError("")}}>{mode==="login" ? "Create a new Developer OS account" : "I already have an account"}</button>
    </div>
  </div>;
}

function Dashboard({ go }) {
  const [data, setData] = useState(null);
  const [projects, setProjects] = useState([]);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  const load = () => {
    Promise.all([
      apiFetch("/workspace/summary/").then(r=>r.json()),
      apiFetch("/projects/").then(r=>r.json()),
    ]).then(([a,p]) => {setData(a); setProjects(Array.isArray(p)?p:(p.results||[]));}).catch(e=>setError(e.message));
  };
  useEffect(load, []);

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await apiFetch("/projects/", {method:"POST", body:JSON.stringify({title:name.trim(),description:"",category:"General",status:"Planning",priority:"medium",tags:[],stack:[]})});
      setName(""); load();
    } catch(e) { setError(e.message); } finally {setBusy(false);}
  };

  const stats = [
    ["PROJECTS", data?.projects ?? "—", "workspace"],
    ["ACTIVE TASKS", data?.active_tasks ?? "—", `${data?.urgent_tasks || 0} urgent`],
    ["COMPLETION", `${data?.completion ?? 0}%`, `${data?.done_tasks || 0} shipped`],
    ["BLOCKED", data?.blocked_tasks ?? "—", `${data?.overdue_tasks || 0} overdue`],
  ];

  return <div className="page">
    <div className="hero-row"><div><div className="eyebrow">DEVELOPER OS / 01</div><h1>Command Center</h1><p>One control plane for building, reasoning, collaborating and shipping software.</p></div><div className="hero-actions"><button className="ghost" onClick={()=>go("/ide")}>OPEN IDE ⌘</button><button className="primary" onClick={()=>document.getElementById("new-project")?.focus()}>+ NEW PROJECT</button></div></div>
    <div className="stat-grid">{stats.map(s=><div className="stat-card" key={s[0]}><span>{s[0]}</span><strong>{s[1]}</strong><small>{s[2]}</small></div>)}</div>
    <div className="dashboard-grid">
      <section className="panel wide-panel"><div className="panel-head"><div><span className="panel-kicker">DELIVERY GRAPH</span><h2>Project trajectory</h2></div><button className="text-btn" onClick={()=>go("/projects")}>VIEW ALL →</button></div>
        <div className="project-list">{(data?.project_completion||[]).map(p=><div className="project-line" key={p.id} onClick={()=>go(`/projects/${p.id}`)}><div><b>{p.title}</b><small>{p.status} · {p.tasks} tasks</small></div><div className="bar"><i style={{width:`${p.progress}%`}} /></div><strong>{p.progress}%</strong></div>)}
        {!data?.project_completion?.length && <div className="empty">No project signals yet. Create the first project.</div>}</div>
      </section>
      <section className="panel intelligence-card"><div className="ai-orb">✦</div><span className="panel-kicker">INTELLIGENCE ENGINE</span><h2>Context-aware AI</h2><p>Ask about your projects, tasks, notes, snippets and delivery risks.</p><button className="primary wide" onClick={()=>go("/ai")}>OPEN INTELLIGENCE →</button></section>
    </div>
    <section className="panel"><div className="panel-head"><div><span className="panel-kicker">PROJECTS</span><h2>Workspace</h2></div><div className="inline-create"><input id="new-project" value={name} onChange={e=>setName(e.target.value)} onKeyDown={e=>e.key==="Enter"&&create()} placeholder="New project name..." /><button className="primary" disabled={busy} onClick={create}>CREATE</button></div></div>
      {error&&<div className="error">{error}</div>}
      <div className="cards-grid">{projects.slice(0,6).map(p=><button className="project-card" key={p.id} onClick={()=>go(`/projects/${p.id}`)}><span>{p.category||"GENERAL"}</span><b>{p.title}</b><small>{p.description||"No description yet."}</small><div className="card-meta"><i>{p.status}</i><strong>{p.progress??0}%</strong></div></button>)}</div>
    </section>
  </div>;
}

function Projects({ go }) {
  const [items,setItems]=useState([]); const [q,setQ]=useState(""); const [form,setForm]=useState(""); const [busy,setBusy]=useState(false);
  const load=()=>apiFetch("/projects/").then(r=>r.json()).then(d=>setItems(Array.isArray(d)?d:d.results||[]));
  useEffect(load,[]);
  const filtered=useMemo(()=>items.filter(p=>(p.title||"").toLowerCase().includes(q.toLowerCase())),[items,q]);
  const create=async()=>{if(!form.trim())return;setBusy(true);await apiFetch("/projects/",{method:"POST",body:JSON.stringify({title:form,category:"General",status:"Planning",priority:"medium",tags:[],stack:[]})});setForm("");setBusy(false);load();};
  return <div className="page"><div className="hero-row"><div><div className="eyebrow">WORKSPACE / PROJECTS</div><h1>Projects</h1><p>Projects are the source of truth for execution, context and collaboration.</p></div></div>
    <div className="toolbar"><div className="global-search large"><span>⌕</span><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Filter projects..." /></div><div className="inline-create"><input value={form} onChange={e=>setForm(e.target.value)} placeholder="Create project..." onKeyDown={e=>e.key==="Enter"&&create()}/><button className="primary" onClick={create}>{busy?"...":"CREATE"}</button></div></div>
    <div className="cards-grid projects-grid">{filtered.map(p=><button className="project-card large-card" key={p.id} onClick={()=>go(`/projects/${p.id}`)}><div className="card-top"><span>{p.category}</span><i>{p.priority}</i></div><b>{p.title}</b><small>{p.description||"Workspace ready for context."}</small><div className="bar"><i style={{width:`${p.progress||0}%`}} /></div><div className="card-meta"><span>{p.status}</span><strong>{p.progress||0}%</strong></div></button>)}</div>
  </div>;
}

function ProjectDetail({ id, go }) {
  const [project,setProject]=useState(null); const [tasks,setTasks]=useState([]); const [comments,setComments]=useState([]); const [comment,setComment]=useState(""); const [tab,setTab]=useState("overview");
  const load=()=>Promise.all([apiFetch(`/projects/${id}/`).then(r=>r.json()),apiFetch(`/tasks/?project=${id}`).then(r=>r.json()),apiFetch(`/comments/?project=${id}`).then(r=>r.json())]).then(([p,t,c])=>{setProject(p);setTasks(Array.isArray(t)?t:[]);setComments(c||[]);});
  useEffect(load,[id]);
  const addComment=async()=>{if(!comment.trim())return;await apiFetch("/comments/",{method:"POST",body:JSON.stringify({project:id,body:comment})});setComment("");load();};
  if(!project)return <div className="page"><div className="loading">LOADING PROJECT...</div></div>;
  return <div className="page"><button className="back" onClick={()=>go("/projects")}>← PROJECTS</button><div className="project-hero"><div><div className="eyebrow">{project.category} / {project.status}</div><h1>{project.title}</h1><p>{project.description||"No project description."}</p></div><button className="primary" onClick={()=>go("/ide")}>OPEN IN IDE ⌘</button></div>
    <div className="tabs">{["overview","tasks","collaboration"].map(t=><button className={tab===t?"selected":""} onClick={()=>setTab(t)} key={t}>{t}</button>)}</div>
    {tab==="overview"&&<div className="dashboard-grid"><section className="panel"><span className="panel-kicker">PROJECT SIGNAL</span><h2>{project.progress||0}% delivered</h2><div className="big-bar"><i style={{width:`${project.progress||0}%`}}/></div><div className="metric-row"><span>Status <b>{project.status}</b></span><span>Priority <b>{project.priority}</b></span><span>Tasks <b>{project.task_count||tasks.length}</b></span></div></section><section className="panel"><span className="panel-kicker">LIVE DISCUSSION</span><div className="comment-box">{comments.slice(0,6).map(c=><div className="comment" key={c.id}><b>{c.author_name}</b><span>{c.body}</span></div>)}{!comments.length&&<div className="empty">Start the project conversation.</div>}</div><div className="comment-input"><input value={comment} onChange={e=>setComment(e.target.value)} onKeyDown={e=>e.key==="Enter"&&addComment()} placeholder="Write a project update..." /><button onClick={addComment}>POST</button></div></section></div>}
    {tab==="tasks"&&<section className="panel"><div className="panel-head"><h2>Execution queue</h2><span>{tasks.length} tasks</span></div>{tasks.map(t=><div className="task-row" key={t.id}><span className={`task-dot ${t.status}`}/><b>{t.title}</b><small>{t.status} · {t.priority}</small>{t.assignee&&<i>@{t.assignee}</i>}</div>)}{!tasks.length&&<div className="empty">No tasks yet.</div>}</section>}
    {tab==="collaboration"&&<Collab projectId={id}/>}
  </div>;
}

function Collab({projectId}) {
  const [members,setMembers]=useState([]); const [identifier,setIdentifier]=useState(""); const [role,setRole]=useState("developer"); const [orgs,setOrgs]=useState([]);
  const load=()=>Promise.all([apiFetch(`/projects/${projectId}/collaborators/`).then(r=>r.json()),apiFetch("/organizations/").then(r=>r.json())]).then(([m,o])=>{setMembers(m);setOrgs(o)});
  useEffect(load,[projectId]);
  const add=async()=>{if(!identifier)return;await apiFetch(`/projects/${projectId}/collaborators/`,{method:"POST",body:JSON.stringify({username:identifier,email:identifier,role})});setIdentifier("");load();};
  return <div className="dashboard-grid"><section className="panel"><div className="panel-head"><h2>Project members</h2><span>{members.length}</span></div><div className="member-list">{members.map(m=><div className="member"><span className="avatar">{m.username[0].toUpperCase()}</span><div><b>{m.full_name}</b><small>@{m.username} · {m.role}</small></div></div>)}</div><div className="invite-row"><input value={identifier} onChange={e=>setIdentifier(e.target.value)} placeholder="Username or email"/><select value={role} onChange={e=>setRole(e.target.value)}><option>developer</option><option>admin</option><option>viewer</option></select><button className="primary" onClick={add}>ADD</button></div></section><section className="panel"><span className="panel-kicker">ORGANIZATION LAYER</span><h2>{orgs.length} organization(s)</h2><p>Teams, roles, plans and API access are persisted in the platform layer.</p><button className="ghost" onClick={()=>window.location.href="/team"}>OPEN TEAM CONTROL →</button></section></div>;
}

function IDE() {
  const [workspaces,setWorkspaces]=useState([]); const [ws,setWs]=useState(null); const [active,setActive]=useState("main.py"); const [terminal,setTerminal]=useState(["Developer OS Web IDE v1.0","Ready. Workspace runtime is local to your browser + API."]); const [saving,setSaving]=useState(false);
  const load=()=>apiFetch("/ide/workspaces/").then(r=>r.json()).then(d=>{setWorkspaces(d);if(d[0]){setWs(d[0]);setActive(d[0].active_file||Object.keys(d[0].files||{})[0]);}});
  useEffect(load,[]);
  const create=async()=>{const r=await apiFetch("/ide/workspaces/",{method:"POST",body:JSON.stringify({name:`Workspace ${workspaces.length+1}`})});const d=await r.json();setWorkspaces([d,...workspaces]);setWs(d);setActive(d.active_file);};
  const save=async()=>{if(!ws)return;setSaving(true);const r=await apiFetch("/ide/workspaces/",{method:"PATCH",body:JSON.stringify({id:ws.id,files:ws.files,active_file:active})});setWs(await r.json());setSaving(false);setTerminal(t=>[...t,`✓ Saved ${active} at ${new Date().toLocaleTimeString()}`]);};
  const code=ws?.files?.[active]??"";
  const updateCode=(value)=>setWs({...ws,files:{...ws.files,[active]:value}});
  const run=()=>{setTerminal(t=>[...t,`$ run ${active}`,`✓ Execution sandbox queued. Connect a runner/worker to execute untrusted code server-side.`]);};
  const addFile=()=>{const n=prompt("File name","app.py");if(n){setWs({...ws,files:{...ws.files,[n]:""}});setActive(n);}};
  return <div className="ide-page"><div className="ide-top"><div><span className="eyebrow">DEVELOPER OS / WEB IDE</span><h1>Command IDE</h1></div><div className="ide-actions"><button onClick={create}>+ WORKSPACE</button><button onClick={addFile} disabled={!ws}>+ FILE</button><button onClick={run} disabled={!ws}>▶ RUN</button><button className="primary" onClick={save} disabled={!ws}>{saving?"SAVING":"SAVE ⌘S"}</button></div></div>
    <div className="ide-frame">
      <aside className="file-tree"><div className="tree-head">EXPLORER <button onClick={addFile}>+</button></div>{workspaces.map(w=><button className={`workspace-select ${ws?.id===w.id?"on":""}`} onClick={()=>{setWs(w);setActive(w.active_file||Object.keys(w.files)[0])}} key={w.id}>◈ {w.name}</button>)}{ws&&<div className="files">{Object.keys(ws.files||{}).map(f=><button className={active===f?"file-on":""} onClick={()=>setActive(f)} key={f}><span>{f.endsWith(".py")?"◉":f.endsWith(".md")?"▤":"□"}</span>{f}</button>)}</div>}{!workspaces.length&&<div className="tree-empty">Create a workspace to begin.</div>}</aside>
      <section className="editor-core"><div className="editor-tabs">{ws&&Object.keys(ws.files||{}).map(f=><button className={active===f?"editor-tab on": "editor-tab"} onClick={()=>setActive(f)} key={f}>{f} <span>×</span></button>)}</div>{ws?<><div className="editor-meta"><span>● {active}</span><span>{(code.match(/\n/g)||[]).length+1} lines</span><span>{ws.language}</span></div><textarea className="code-editor" spellCheck="false" value={code} onChange={e=>updateCode(e.target.value)} onKeyDown={e=>{if((e.ctrlKey||e.metaKey)&&e.key==="s"){e.preventDefault();save();}}}/></>:<div className="editor-empty"><div>⌘</div><h2>Web IDE ready</h2><p>Persistent workspaces, file tree, editor, terminal and project context.</p><button className="primary" onClick={create}>CREATE WORKSPACE</button></div>}<div className="terminal"><div className="terminal-head"><span>TERMINAL</span><button onClick={()=>setTerminal([])}>CLEAR</button></div>{terminal.map((x,i)=><div key={i}>{x}</div>)}</div></section>
    </div></div>;
}

function AI() {
  const [conversations,setConversations]=useState([]); const [conversation,setConversation]=useState(null); const [messages,setMessages]=useState([]); const [input,setInput]=useState(""); const [busy,setBusy]=useState(false); const bottom=useRef(null);
  useEffect(()=>{apiFetch("/ai/conversations/").then(r=>r.json()).then(setConversations).catch(()=>{});},[]);
  useEffect(()=>{bottom.current?.scrollIntoView({behavior:"smooth"});},[messages]);
  const open=async id=>{const c=conversations.find(x=>x.id===id);setConversation(c);const r=await apiFetch(`/ai/conversations/${id}/messages/`);setMessages(await r.json());};
  const send=async()=>{if(!input.trim()||busy)return;const text=input.trim();setInput("");setMessages(m=>[...m,{role:"user",content:text}]);setBusy(true);try{const r=await apiFetch("/ai/chat/",{method:"POST",body:JSON.stringify({message:text,conversation:conversation?.id})});const d=await r.json();setConversation(d.conversation);setMessages(m=>[...m,d.message]);if(!conversation)setConversations(c=>[d.conversation,...c]);}catch(e){setMessages(m=>[...m,{role:"assistant",content:`Engine error: ${e.message}`}]);}finally{setBusy(false);}};
  return <div className="page ai-page"><div className="hero-row"><div><div className="eyebrow">INTELLIGENCE LAYER</div><h1>Developer Intelligence</h1><p>Context-aware reasoning over your actual workspace. No invented project facts.</p></div><div className="ai-status"><i/> CONTEXT ENGINE ONLINE</div></div>
    <div className="ai-layout"><aside className="panel ai-history"><button className="primary wide" onClick={()=>{setConversation(null);setMessages([])}}>+ NEW THREAD</button><div className="history-label">THREADS</div>{conversations.map(c=><button className={conversation?.id===c.id?"history-on":""} onClick={()=>open(c.id)} key={c.id}>{c.title}</button>)}</aside><section className="panel chat"><div className="chat-head"><span>✦</span><div><b>{conversation?.title||"Workspace Intelligence"}</b><small>Projects · Tasks · Notes · Snippets · GitHub context</small></div></div><div className="messages">{!messages.length&&<div className="ai-welcome"><div className="ai-orb">✦</div><h2>What are we building next?</h2><p>Ask for architecture review, delivery risks, task planning, code review or project analysis.</p><div className="prompt-chips">{["Review my workspace","Find delivery risks","Plan the next milestone","Review my architecture"].map(x=><button onClick={()=>setInput(x)} key={x}>{x}</button>)}</div></div>}{messages.map((m,i)=><div className={`message ${m.role}`} key={m.id||i}><span>{m.role==="user"?"YOU":"DOS"}</span><div>{m.content}</div></div>)}<div ref={bottom}/></div><div className="chat-input"><textarea value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}}} placeholder="Ask Developer OS anything about your workspace..." /><button className="primary" disabled={busy} onClick={send}>{busy?"THINKING...":"SEND →"}</button></div></section></div>
  </div>;
}

function SearchPage() {
  const params=new URLSearchParams(window.location.search); const [q,setQ]=useState(params.get("q")||""); const [results,setResults]=useState([]);
  useEffect(()=>{if(q)apiFetch(`/platform/search/?q=${encodeURIComponent(q)}`).then(r=>r.json()).then(d=>setResults(d.results||[])).catch(()=>{});},[q]);
  return <div className="page"><div className="hero-row"><div><div className="eyebrow">KNOWLEDGE GRAPH / SEARCH</div><h1>Universal Search</h1><p>Projects, tasks, notes, snippets and developer catalog — one index.</p></div></div><div className="search-big"><span>⌕</span><input autoFocus value={q} onChange={e=>setQ(e.target.value)} placeholder="Search your entire Developer OS..." /></div><div className="results">{results.map((r,i)=><div className="result" key={`${r.type}-${r.id}-${i}`}><span>{r.type}</span><div><b>{r.title}</b><p>{r.subtitle}</p></div><strong>→</strong></div>)}{q&&!results.length&&<div className="empty">No results for “{q}”.</div>}</div></div>;
}

function Team() {
  const [orgs,setOrgs]=useState([]); const [members,setMembers]=useState([]); const [name,setName]=useState(""); const [selected,setSelected]=useState(null); const [identifier,setIdentifier]=useState("");
  const load=()=>apiFetch("/organizations/").then(r=>r.json()).then(d=>{setOrgs(d);if(d[0]&&!selected)setSelected(d[0])});
  useEffect(load,[]);
  useEffect(()=>{if(selected)apiFetch(`/organizations/${selected.id}/members/`).then(r=>r.json()).then(setMembers).catch(()=>setMembers([]));},[selected]);
  const create=async()=>{if(!name)return;await apiFetch("/organizations/",{method:"POST",body:JSON.stringify({name})});setName("");load();};
  const add=async()=>{if(!selected||!identifier)return;await apiFetch(`/organizations/${selected.id}/members/`,{method:"POST",body:JSON.stringify({username:identifier,role:"developer"})});setIdentifier("");load();};
  return <div className="page"><div className="hero-row"><div><div className="eyebrow">COLLABORATION FABRIC</div><h1>Team Control</h1><p>Organizations, roles, membership and project collaboration.</p></div></div><div className="dashboard-grid"><section className="panel"><div className="panel-head"><h2>Organizations</h2></div><div className="org-create"><input value={name} onChange={e=>setName(e.target.value)} placeholder="Organization name"/><button className="primary" onClick={create}>CREATE</button></div>{orgs.map(o=><button className={`org-row ${selected?.id===o.id?"selected":""}`} onClick={()=>setSelected(o)} key={o.id}><b>{o.name}</b><span>{o.plan}</span></button>)}{!orgs.length&&<div className="empty">Create your team space.</div>}</section><section className="panel"><div className="panel-head"><h2>{selected?.name||"Select organization"}</h2><span>{members.length} members</span></div>{selected&&<div className="invite-row"><input value={identifier} onChange={e=>setIdentifier(e.target.value)} placeholder="Username or email"/><button className="primary" onClick={add}>INVITE</button></div>}{members.map(m=><div className="member" key={m.id}><span className="avatar">{m.username[0].toUpperCase()}</span><div><b>{m.username}</b><small>{m.email} · {m.role}</small></div></div>)}</section></div></div>;
}

function Billing() {
  const [sub,setSub]=useState(null); const [keys,setKeys]=useState([]); const [newKey,setNewKey]=useState("");
  const load=()=>Promise.all([apiFetch("/subscription/").then(r=>r.json()),apiFetch("/api-keys/").then(r=>r.json())]).then(([s,k])=>{setSub(s);setKeys(k)});
  useEffect(load,[]);
  const upgrade=async plan=>{await apiFetch("/subscription/",{method:"POST",body:JSON.stringify({plan})});load();};
  const createKey=async()=>{const r=await apiFetch("/api-keys/",{method:"POST",body:JSON.stringify({name:"Developer OS CLI"})});const d=await r.json();setNewKey(d.key);load();};
  return <div className="page"><div className="hero-row"><div><div className="eyebrow">SAAS CONTROL PLANE</div><h1>Plans & API</h1><p>Persistent entitlements, subscription state and developer API credentials.</p></div></div><div className="plan-grid">{[["free","FREE","Core workspace"],["pro","PRO","AI + advanced automation"],["team","TEAM","Organizations + collaboration"],["enterprise","ENTERPRISE","Custom controls"]].map(p=><div className={`plan ${sub?.plan===p[0]?"current":""}`} key={p[0]}><span>{p[1]}</span><h2>{p[2]}</h2><p>{sub?.plan===p[0]?"CURRENT PLAN":"Available entitlement tier"}</p><button className={sub?.plan===p[0]?"ghost":"primary"} onClick={()=>upgrade(p[0])}>{sub?.plan===p[0]?"ACTIVE":"SELECT"}</button></div>)}</div><section className="panel"><div className="panel-head"><div><span className="panel-kicker">DEVELOPER API</span><h2>API keys</h2></div><button className="primary" onClick={createKey}>+ CREATE KEY</button></div>{newKey&&<div className="secret-key"><b>Copy this key now — it will not be shown again:</b><code>{newKey}</code></div>}{keys.map(k=><div className="key-row" key={k.id}><code>{k.prefix}••••••••</code><span>{k.name}</span><small>{k.revoked_at?"REVOKED":"ACTIVE"}</small></div>)}</section></div>;
}

function Settings() {
  const [profile,setProfile]=useState(null); const [saved,setSaved]=useState(false);
  useEffect(()=>apiFetch("/profile/").then(r=>r.json()).then(setProfile).catch(()=>{}),[]);
  const save=async()=>{await apiFetch("/profile/",{method:"PATCH",body:JSON.stringify(profile)});setSaved(true);setTimeout(()=>setSaved(false),1800);};
  if(!profile)return <div className="page loading">LOADING PROFILE...</div>;
  return <div className="page"><div className="hero-row"><div><div className="eyebrow">SYSTEM / IDENTITY</div><h1>Settings</h1><p>Control your Developer OS identity and account surface.</p></div></div><section className="panel settings-form"><label>FULL NAME<input value={profile.full_name||""} onChange={e=>setProfile({...profile,full_name:e.target.value})}/></label><label>BIO<textarea value={profile.bio||""} onChange={e=>setProfile({...profile,bio:e.target.value})}/></label><label>GITHUB<input value={profile.github||""} onChange={e=>setProfile({...profile,github:e.target.value})}/></label><label>WEBSITE<input value={profile.website||""} onChange={e=>setProfile({...profile,website:e.target.value})}/></label><button className="primary" onClick={save}>{saved?"SAVED ✓":"SAVE CHANGES"}</button></section></div>;
}

export default function App() {
  const [authenticated,setAuthenticated]=useState(Boolean(getAccessToken()));
  const [user,setUser]=useState(null);
  const [path,go]=useRoute();

  useEffect(()=>{if(authenticated)apiFetch("/profile/").then(r=>r.json()).then(p=>setUser(p.user||p)).catch(()=>setAuthenticated(false));},[authenticated]);
  useEffect(()=>{const f=()=>setAuthenticated(false);window.addEventListener("auth:expired",f);const k=e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="k"){e.preventDefault();document.querySelector(".global-search input")?.focus();}};window.addEventListener("keydown",k);return()=>{window.removeEventListener("auth:expired",f);window.removeEventListener("keydown",k)};},[]);

  if(!authenticated)return <Auth onReady={()=>setAuthenticated(true)}/>;
  if(!user)return <div className="boot">INITIALIZING DEVELOPER OS <span>██████████</span></div>;

  const projectMatch=path.match(/^\/projects\/(\d+)/);
  let current=path==="/"?"dashboard":path.split("/")[1]||"dashboard";
  let content;
  if(projectMatch) content=<ProjectDetail id={projectMatch[1]} go={go}/>;
  else if(current==="dashboard") content=<Dashboard go={go}/>;
  else if(current==="projects") content=<Projects go={go}/>;
  else if(current==="ide") content=<IDE/>;
  else if(current==="ai") content=<AI/>;
  else if(current==="search") content=<SearchPage/>;
  else if(current==="team") content=<Team/>;
  else if(current==="billing") content=<Billing/>;
  else if(current==="settings") content=<Settings/>;
  else content=<Dashboard go={go}/>;

  return <Shell user={user} onLogout={()=>setAuthenticated(false)} go={go} current={current}>{content}</Shell>;
}
