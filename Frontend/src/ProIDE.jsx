import { useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "./services/api";
import "./ProIDE.css";

const extLanguage = (path) => {
  const ext = (path.split(".").pop() || "").toLowerCase();
  return ({js:"JavaScript",jsx:"React JSX",ts:"TypeScript",tsx:"React TSX",py:"Python",html:"HTML",css:"CSS",json:"JSON",md:"Markdown",yml:"YAML",yaml:"YAML",sql:"SQL",sh:"Shell",env:"Env",go:"Go",rs:"Rust",java:"Java",php:"PHP"}[ext] || "Text");
};

function Tree({ files, active, onOpen }) {
  const paths = Object.keys(files).sort();
  return <div className="ide-tree">
    <div className="ide-tree-head">EXPLORER <span>{paths.length} files</span></div>
    {paths.map(path => <button key={path} className={`ide-file ${path === active ? "active" : ""}`} onClick={() => onOpen(path)}>
      <span className="file-icon">{path.endsWith(".json") ? "{}" : path.endsWith(".py") ? "Py" : path.endsWith(".jsx") || path.endsWith(".tsx") ? "⚛" : "·"}</span>
      <span>{path}</span>
    </button>)}
    {!paths.length && <div className="ide-empty">No files yet.</div>}
  </div>;
}

export default function ProIDE({ projectId, message }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [ws, setWs] = useState(null);
  const [files, setFiles] = useState({});
  const [active, setActive] = useState("");
  const [frameworks, setFrameworks] = useState([]);
  const [framework, setFramework] = useState("react-vite");
  const [packages, setPackages] = useState("");
  const [terminal, setTerminal] = useState("");
  const [command, setCommand] = useState("");
  const [status, setStatus] = useState("Ready");
  const [saving, setSaving] = useState(false);
  const [showTerminal, setShowTerminal] = useState(true);
  const editorRef = useRef(null);

  useEffect(() => {
    Promise.all([apiFetch("/ide/workspaces/"), apiFetch("/ide/frameworks/")])
      .then(async ([a,b]) => { setWorkspaces(await a.json()); setFrameworks(await b.json()); })
      .catch(e => message?.(e.message));
  }, []);

  useEffect(() => {
    if (!ws && workspaces[0]) openWorkspace(workspaces[0]);
  }, [workspaces, ws]);

  async function openWorkspace(item) {
    setWs(item); setFiles(item.files || {}); setActive(item.active_file || Object.keys(item.files || {})[0] || "");
    setStatus("Workspace loaded");
  }

  async function createWorkspace() {
    const name = window.prompt("Workspace name", "My Developer OS App");
    if (!name) return;
    const res = await apiFetch("/ide/workspaces/", { method:"POST", body:JSON.stringify({
      name, project: projectId || null, framework: "", runtime: "node", package_manager: "npm",
      files: {"README.md":"# "+name+"\n\nBuilt with Developer OS.\n"}
    })});
    const item = await res.json();
    setWorkspaces(x => [item, ...x]); openWorkspace(item);
  }

  function updateContent(value) {
    if (!active) return;
    setFiles(x => ({...x, [active]: value}));
    setStatus("Unsaved changes");
  }

  async function saveFile() {
    if (!ws || !active) return;
    setSaving(true);
    try {
      const res = await apiFetch(`/ide/workspaces/${ws.id}/files/`, {method:"POST", body:JSON.stringify({path:active, content:files[active] || ""})});
      const data = await res.json(); setFiles(data.files || files); setStatus("Saved"); 
    } catch(e) { setStatus(e.message); } finally { setSaving(false); }
  }

  async function newFile() {
    if (!ws) return;
    const path = window.prompt("File path (example: src/App.jsx)", "src/App.jsx");
    if (!path) return;
    if (files[path]) return setStatus("File already exists");
    setFiles(x => ({...x,[path]:""})); setActive(path); setStatus("New file");
    await apiFetch(`/ide/workspaces/${ws.id}/files/`, {method:"POST",body:JSON.stringify({path,content:""})});
  }

  async function renameFile() {
    if (!ws || !active) return;
    const target = window.prompt("Rename / move file", active);
    if (!target || target === active) return;
    try {
      const res = await apiFetch(`/ide/workspaces/${ws.id}/files/`, {method:"POST",body:JSON.stringify({action:"rename",path:active,to:target})});
      const data = await res.json(); setFiles(data.files || files); setActive(data.active_file || target); setStatus("File moved");
    } catch(e) { setStatus(e.message); }
  }

  async function deleteFile() {
    if (!ws || !active || !window.confirm(`Delete ${active}?`)) return;
    const res = await apiFetch(`/ide/workspaces/${ws.id}/files/`, {method:"DELETE",body:JSON.stringify({path:active})});
    const data = await res.json(); setFiles(data.files || {}); setActive(data.active_file || Object.keys(data.files || {})[0] || ""); setStatus("Deleted");
  }

  async function install() {
    if (!ws) return;
    setStatus("Installing framework…"); setTerminal("");
    try {
      const res = await apiFetch(`/ide/workspaces/${ws.id}/install/`, {method:"POST",body:JSON.stringify({framework})});
      const data = await res.json();
      setTerminal(data.installation?.output || data.error || "No output");
      if (data.workspace) { setWs(data.workspace); setFiles(data.workspace.files || files); }
      setStatus(data.installation?.status === "success" ? "Framework installed" : "Install failed");
    } catch(e) { setStatus(e.message); }
  }

  async function installPackages() {
    if (!ws || !packages.trim()) return;
    setStatus("Installing packages…"); setTerminal("");
    try {
      const manager = ws.package_manager || (frameworks.find(f => f.id === framework)?.package_manager) || "npm";
      const res = await apiFetch(`/ide/workspaces/${ws.id}/packages/`, {method:"POST",body:JSON.stringify({package_manager:manager,packages:packages.split(",").map(x=>x.trim()).filter(Boolean)})});
      const data = await res.json();
      setTerminal(`${data.stdout || ""}${data.stderr ? "\n"+data.stderr : ""}`);
      if (data.workspace) { setWs(data.workspace); setFiles(data.workspace.files || files); }
      setPackages("");
      setStatus(data.status === "success" ? "Packages installed" : "Package install failed");
    } catch(e) { setStatus(e.message); }
  }

  async function runCommand(e) {
    e?.preventDefault();
    if (!ws || !command.trim()) return;
    setStatus("Running…");
    try {
      const res = await apiFetch(`/ide/workspaces/${ws.id}/execute/`, {method:"POST",body:JSON.stringify({command})});
      const data = await res.json();
      setTerminal(`${data.stdout || ""}${data.stderr ? "\n"+data.stderr : ""}\n\n[exit ${data.exit_code}]`);
      if (data.files) setFiles(data.files);
      setCommand("");
      setStatus(data.status === "success" ? "Command completed" : "Command failed");
    } catch(e) { setStatus(e.message); }
  }

  const lineNumbers = useMemo(() => String(files[active] || "").split("\n").map((_,i) => i+1).join("\n"), [files, active]);

  return <div className="dos-ide">
    <header className="ide-header">
      <div className="ide-brand"><span className="ide-brand-mark">⌘</span><div><strong>Developer OS IDE</strong><small>{ws?.name || "No workspace"} · {ws?.framework || "polyglot workspace"}</small></div></div>
      <div className="ide-actions">
        <select value={framework} onChange={e=>setFramework(e.target.value)}>{frameworks.map(f=><option key={f.id} value={f.id}>{f.label}</option>)}</select>
        <button onClick={install}>Install framework</button>
        <button onClick={newFile}>＋ File</button>
        <button onClick={saveFile} disabled={saving}>{saving ? "Saving…" : "Save"}</button>
        <button className="primary" onClick={()=>setShowTerminal(x=>!x)}>Terminal</button>
      </div>
    </header>
    <div className="ide-packagebar">
      <span>PACKAGE MANAGER</span>
      <b>{ws?.package_manager || frameworks.find(f=>f.id === framework)?.package_manager || "npm"}</b>
      <input value={packages} onChange={e=>setPackages(e.target.value)} placeholder="Install packages: axios, zod, django-filter…" onKeyDown={e=>{if(e.key==="Enter") installPackages()}} />
      <button onClick={installPackages}>Install packages</button>
    </div>
    <div className="ide-workspacebar">
      <select value={ws?.id || ""} onChange={e=>openWorkspace(workspaces.find(x=>String(x.id)===e.target.value))}>
        {workspaces.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}
      </select>
      <button onClick={createWorkspace}>New workspace</button>
      <span className={`ide-status ${status.includes("failed") ? "bad" : ""}`}>{status}</span>
    </div>
    <div className="ide-main">
      <Tree files={files} active={active} onOpen={setActive}/>
      <section className="ide-center">
        <div className="ide-tabs">
          {active && <div className="ide-tab active"><span>{active.split("/").pop()}</span><em>{extLanguage(active)}</em><button onClick={deleteFile}>×</button></div>}
        </div>
        <div className="ide-editor">
          <pre className="ide-lines">{lineNumbers}</pre>
          <textarea ref={editorRef} value={files[active] || ""} onChange={e=>updateContent(e.target.value)} spellCheck="false" autoCapitalize="off" autoCorrect="off" placeholder="Select a file or create one…"/>
        </div>
        <footer className="ide-footer"><span>{active || "No file selected"}</span><span>{extLanguage(active)} · UTF-8</span><span>{(files[active] || "").length} chars</span></footer>
      </section>
      {showTerminal && <aside className="ide-terminal">
        <div className="terminal-head"><strong>TERMINAL</strong><span>Sandbox · 120s max</span></div>
        <pre>{terminal || "Developer OS secure runner\n\nInstall a framework or run a command.\nExamples:\n  npm run build\n  python manage.py check\n  python -m pytest"}</pre>
        <form onSubmit={runCommand}><span>›</span><input value={command} onChange={e=>setCommand(e.target.value)} placeholder="Run a command…" /></form>
      </aside>}
    </div>
  </div>;
}
