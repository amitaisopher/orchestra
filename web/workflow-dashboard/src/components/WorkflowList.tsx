import { useEffect, useState } from 'react'

interface WorkflowUpdate {
  workflow_id: string;
  status: string;
  tasks: Array<{
    taskId: string;
    status: string;
    type: string;
  }>;
}

interface WorkflowListProps {
  apiBase: string;
  onSelect: (id: string) => void;
  selectedId: string | null;
  workflowUpdates: WorkflowUpdate[];
}

export default function WorkflowList({ apiBase, onSelect, selectedId, workflowUpdates }: WorkflowListProps) {
  const [items, setItems] = useState<{workflowId:string; status:string}[]>([])
  
  // Load initial workflow list (no polling!)
  useEffect(() => {
    if (!apiBase) return
    const load = async () => {
      const res = await fetch(`${apiBase}/workflows`)
      const data = await res.json()
      setItems(Array.isArray(data) ? data : [])
    }
    load(); // Only load once initially
  }, [apiBase])

  // Update workflow statuses from WebSocket updates
  useEffect(() => {
    if (workflowUpdates.length === 0) return;

    setItems(prevItems => {
      let updatedItems = [...prevItems];
      
      workflowUpdates.forEach(update => {
        // Validate that we have the required data
        if (!update.workflow_id || !update.status) {
          console.warn('Invalid workflow update received:', update);
          return; // Skip invalid updates
        }
        
        const index = updatedItems.findIndex(item => item.workflowId === update.workflow_id);
        if (index !== -1) {
          // Update existing workflow
          updatedItems[index] = { ...updatedItems[index], status: update.status };
        } else {
          // Add new workflow if not exists (with validation)
          updatedItems.push({ 
            workflowId: update.workflow_id, 
            status: update.status 
          });
        }
      });
      
      return updatedItems;
    });
  }, [workflowUpdates])
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
