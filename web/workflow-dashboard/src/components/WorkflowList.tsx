import { useEffect, useState } from 'react'

export default function WorkflowList({ apiBase, onSelect, selectedId }:{ apiBase:string; onSelect:(id:string)=>void; selectedId:string|null }) {
  const [items, setItems] = useState<{workflowId:string; status:string}[]>([])
  useEffect(() => {
    if (!apiBase) return
    const load = async () => {
      const res = await fetch(`${apiBase}/workflows`)
      const data = await res.json()
      setItems(Array.isArray(data) ? data : [])
    }
    load(); const t = setInterval(load, 5000); return () => clearInterval(t)
  }, [apiBase])
  return (
    <ul style={{ listStyle:'none', padding:0, marginTop:16 }}>
      {items.map(w => (
        <li key={w.workflowId}
            style={{ padding:8, cursor:'pointer', background:selectedId===w.workflowId?'#eef':'#fff' }}
            onClick={() => onSelect(w.workflowId)}>
          <div style={{ fontWeight:600, color:'#333' }}>{w.workflowId}</div>
          <div style={{ fontSize:12, color:'#666' }}>status: {w.status}</div>
        </li>
      ))}
    </ul>
  )
}
