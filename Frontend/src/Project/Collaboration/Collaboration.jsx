import { useEffect, useState } from "react";
import { apiFetch } from "../../services/api";
import "./Collaboration.css";

export default function CollaborationPage({ setPage, project }) {
  const [members,setMembers]=useState([]); const [identifier,setIdentifier]=useState(""); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  const [activeProject,setActiveProject]=useState(project || null);
  const projectId=activeProject?.id;
  useEffect(()=>{ if(project?.id){setActiveProject(project);return;} apiFetch("/projects/").then(r=>r.json()).then(items=>setActiveProject(items?.[0]||null)).catch(e=>setError(e.message)); },[project]);
  useEffect(()=>{if(projectId)apiFetch(`/projects/${projectId}/collaborators/`).then(r=>r.json()).then(setMembers).catch(e=>setError(e.message));},[projectId]);
  async function add(e){e.preventDefault();if(!identifier.trim()||!projectId)return;setBusy(true);setError("");try{const r=await apiFetch(`/projects/${projectId}/collaborators/`,{method:"POST",body:JSON.stringify({username:identifier})});const m=await r.json();setMembers(x=>x.some(v=>v.id===m.id)?x:[...x,m]);setIdentifier("")}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function remove(m){try{await apiFetch(`/projects/${projectId}/collaborators/`,{method:"DELETE",body:JSON.stringify({username:m.username})});setMembers(x=>x.filter(v=>v.id!==m.id))}catch(e){setError(e.message)}}
  return <main className="collab-page"><div className="collab-head"><div><span>REAL PROJECT MEMBERSHIP</span><h2>Collaboration</h2><p>{activeProject ? `Managing access for ${activeProject.title}.` : "Select or create a project to manage members."}</p></div><button onClick={()=>setPage("dashboard")}>Back to workspace</button></div>{!projectId?<div className="collab-empty">No project is available yet. Create one in the workspace first.</div>:<div className="collab-grid"><section className="collab-card"><header><b>Members</b><small>{members.length}</small></header>{members.map(m=><div className="member" key={m.id}><div className="member-avatar">{m.username.slice(0,1).toUpperCase()}</div><div><strong>{m.full_name||m.username}</strong><small>@{m.username} · {m.role}</small></div>{m.role!=="owner"&&<button onClick={()=>remove(m)}>Remove</button>}</div>)}</section><section className="collab-card"><header><b>Add collaborator</b><small>REGISTERED USERS</small></header><form onSubmit={add}><input value={identifier} onChange={e=>setIdentifier(e.target.value)} placeholder="Username or email"/><button disabled={busy}>{busy?"Adding…":"Add member"}</button></form><p className="collab-note">Project access is enforced by the API. Members can be added or removed by the project owner.</p>{error&&<div className="collab-error">{error}</div>}</section></div>}</main>
}
