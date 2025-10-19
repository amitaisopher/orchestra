import { useEffect, useState } from 'react'
import WorkflowGraph from './components/WorkflowGraph'
import WorkflowList from './components/WorkflowList'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE as string | undefined

export default function App() {
  const [apiBase, setApiBase] = useState(''); const [selectedId, setSelectedId] = useState<string|null>(null)
  const [workflow, setWorkflow] = useState<any|null>(null)
  
  useEffect(() => { setApiBase(API_BASE ?? '') }, [])
  useEffect(() => {
    if (!apiBase || !selectedId) return
    const load = async () => {
      const res = await fetch(`${apiBase}/workflows/${selectedId}`)
      setWorkflow(await res.json())
    }
    load(); const t = setInterval(load, 3000); return () => clearInterval(t)
  }, [apiBase, selectedId])
  return (
    <div style={{ display:'grid', gridTemplateColumns:'320px 1fr', height:'100vh' }}>
      <div style={{ padding:16, borderRight:'1px solid #eee' }}>
        <h2>Workflows</h2>
        <StartWorkflow apiBase={apiBase} onStarted={(id)=>setSelectedId(id)} />
        <WorkflowList apiBase={apiBase} onSelect={setSelectedId} selectedId={selectedId} />
      </div>
      <div style={{ padding:16, width: '100%', height: '100%', overflow: 'hidden' }}>
        <h2>Execution DAG</h2>
        <WorkflowGraph workflow={workflow} />
      </div>
    </div>
  )
}

function StartWorkflow({ apiBase, onStarted }:{ apiBase:string; onStarted:(id:string)=>void }) {
  const [id, setId] = useState('wf-' + Date.now()); const disabled = !apiBase
  const start = async () => {
    const res = await fetch(`${apiBase}/workflows`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ workflowId:id }) })
    if (res.ok) onStarted(id)
  }
  return (
    <div style={{ display:'grid', gap:8 }}>
      <input value={id} onChange={e=>setId(e.target.value)} placeholder="workflow id" />
      <button disabled={disabled} onClick={start}>Start workflow</button>
    </div>
  )
}
