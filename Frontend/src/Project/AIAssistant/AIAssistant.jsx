import { useState } from "react";
import { apiFetch } from "../../services/api";
import "./AIAssistant.css";

export default function AIAssistantPage({ setPage }) {
  const [message,setMessage]=useState(""); const [answer,setAnswer]=useState(""); const [mode,setMode]=useState(""); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  async function ask(e){e.preventDefault();if(!message.trim())return;setBusy(true);setError("");try{const r=await apiFetch("/assistant/",{method:"POST",body:JSON.stringify({message})});const d=await r.json();setAnswer(d.answer);setMode(d.mode);}catch(e){setError(e.message)}finally{setBusy(false)}}
  const prompts=["What should I work on next?","Summarize the current delivery risks.","Help me plan the next milestone."];
  return <main className="ai-page"><div className="ai-head"><div><span>DEVELOPER COPILOT</span><h2>AI assistant</h2><p>Context-aware help grounded in your actual workspace. Optional external AI can be enabled with environment variables.</p></div><button onClick={()=>setPage("dashboard")}>Back to workspace</button></div><div className="ai-layout"><section className="ai-card"><div className="ai-badge">AI / WORKSPACE CONTEXT</div>{answer?<div className="ai-answer"><small>{mode === "provider" ? "External model" : "Local workspace intelligence"}</small><p>{answer}</p></div>:<div className="ai-empty">Ask a project question and DeveloperOS will analyze your current tasks, deadlines, priorities and completion state.</div>}<form onSubmit={ask}><textarea value={message} onChange={e=>setMessage(e.target.value)} placeholder="Ask about your projects, tasks, delivery or next steps…"/><button disabled={busy}>{busy?"Analyzing…":"Ask assistant"}</button></form>{error&&<div className="ai-error">{error}</div>}</section><aside className="ai-card"><h3>Quick prompts</h3>{prompts.map(p=><button className="prompt" key={p} onClick={()=>setMessage(p)}>{p}<span>→</span></button>)}</aside></div></main>
}
