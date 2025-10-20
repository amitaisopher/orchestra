import { useEffect, useState } from 'react'
import WorkflowGraph from './components/WorkflowGraph'
import WorkflowList from './components/WorkflowList'
import { useWebSocket } from './hooks/useWebSocket'
import './App.css'

// Runtime configuration - loaded from config.js file deployed by CDK
declare global {
  interface Window {
    API_BASE?: string;
    WEBSOCKET_URL?: string;
  }
}

const API_BASE = window.API_BASE || import.meta.env.VITE_API_BASE as string | undefined
const WEBSOCKET_URL = window.WEBSOCKET_URL || import.meta.env.VITE_WEBSOCKET_URL as string | undefined

export default function App() {
  const [apiBase, setApiBase] = useState('');
  const [websocketUrl, setWebsocketUrl] = useState('');
  const [selectedId, setSelectedId] = useState<string|null>(null)
  const [workflow, setWorkflow] = useState<any|null>(null)
  
  // WebSocket connection for real-time updates
  const { isConnected, workflowUpdates, getWorkflowUpdate } = useWebSocket(websocketUrl || null);
  
  useEffect(() => { 
    // Check for runtime config first, fallback to build-time env
    setApiBase(window.API_BASE || API_BASE || '') 
    setWebsocketUrl(window.WEBSOCKET_URL || WEBSOCKET_URL || '')
  }, [])

  // Load initial workflow data
  useEffect(() => {
    if (!apiBase || !selectedId) return
    const load = async () => {
      const res = await fetch(`${apiBase}/workflows/${selectedId}`)
      setWorkflow(await res.json())
    }
    load();
  }, [apiBase, selectedId])

  // Update workflow with WebSocket data
  useEffect(() => {
    if (!selectedId) return
    const wsUpdate = getWorkflowUpdate(selectedId);
    if (wsUpdate) {
      console.log('Updating workflow with WebSocket data:', wsUpdate);
      setWorkflow((prevWorkflow: any) => ({
        ...prevWorkflow,
        status: wsUpdate.status,
        tasks: wsUpdate.tasks,
      }));
    }
  }, [selectedId, getWorkflowUpdate])
  return (
    <div style={{ display:'grid', gridTemplateColumns:'320px 1fr', height:'100vh' }}>
      <div style={{ padding:16, borderRight:'1px solid #eee' }}>
        <h2>Workflows</h2>
        <div style={{ marginBottom: 8, fontSize: 12, color: isConnected ? 'green' : 'red' }}>
          WebSocket: {isConnected ? 'Connected' : 'Disconnected'}
        </div>
        <StartWorkflow apiBase={apiBase} onStarted={(id)=>setSelectedId(id)} />
        <WorkflowList 
          apiBase={apiBase} 
          onSelect={setSelectedId} 
          selectedId={selectedId} 
          workflowUpdates={workflowUpdates}
        />
      </div>
      <div style={{ padding:16, width: '100%', height: '100%', overflow: 'hidden' }}>
        <h2>Execution DAG</h2>
        <WorkflowGraph workflow={workflow} />
      </div>
    </div>
  )
}

function StartWorkflow({ apiBase, onStarted }:{ apiBase:string; onStarted:(id:string)=>void }) {
  const [isLoading, setIsLoading] = useState(false)
  const disabled = !apiBase || isLoading
  
  const start = async () => {
    // Generate a new workflow ID automatically
    const workflowId = `wf-${Date.now()}-${Math.random().toString(36).substr(2, 6)}`
    
    setIsLoading(true)
    try {
      const res = await fetch(`${apiBase}/workflows`, { 
        method:'POST', 
        headers:{'Content-Type':'application/json'}, 
        body: JSON.stringify({ workflowId }) 
      })
      
      if (res.ok) {
        onStarted(workflowId)
      } else {
        console.error('Failed to start workflow:', await res.text())
        alert('Failed to start workflow. Please try again.')
      }
    } catch (error) {
      console.error('Error starting workflow:', error)
      alert('Error starting workflow. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }
  
  return (
    <div style={{ marginBottom: 16 }}>
      <button 
        disabled={disabled} 
        onClick={start}
        style={{
          width: '100%',
          padding: '12px 16px',
          backgroundColor: disabled ? '#ccc' : '#007bff',
          color: 'white',
          border: 'none',
          borderRadius: '4px',
          cursor: disabled ? 'not-allowed' : 'pointer',
          fontSize: '14px',
          fontWeight: '500'
        }}
      >
        {isLoading ? 'Starting...' : 'Start New Workflow'}
      </button>
    </div>
  )
}
