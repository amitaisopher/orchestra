import { useMemo } from 'react'
import {ReactFlow,  Background, Controls, MiniMap } from '@xyflow/react'
import '@xyflow/react/dist/style.css';

export default function WorkflowGraph({ workflow }:{ workflow:any|null }) {
  const dag = workflow?.dag ?? { A:['B1','B2','B3'], B1:['C'], B2:['C'], B3:['C'], C:[] }
  const tasks:any[] = workflow?.tasks ?? []
  const statusMap = new Map(tasks.map((t:any) => [t.taskId, t.status]))
  const nodes = useMemo(() => {
    const all = Object.keys(dag)
    
    // Create a simple vertical layout based on DAG levels
    const levels = new Map<string, number>()
    const visited = new Set<string>()
    
    // Calculate levels using topological ordering
    const calculateLevel = (node: string): number => {
      if (levels.has(node)) return levels.get(node)!
      if (visited.has(node)) return 0 // Handle cycles
      
      visited.add(node)
      const dependencies = Object.entries(dag)
        .filter(([_, targets]) => (targets as string[]).includes(node))
        .map(([source, _]) => source)
      
      const maxLevel = dependencies.length > 0 
        ? Math.max(...dependencies.map(dep => calculateLevel(dep))) + 1
        : 0
      
      levels.set(node, maxLevel)
      visited.delete(node)
      return maxLevel
    }
    
    // Calculate levels for all nodes
    all.forEach(node => calculateLevel(node))
    
    // Group nodes by level for horizontal spacing
    const nodesByLevel = new Map<number, string[]>()
    levels.forEach((level, node) => {
      if (!nodesByLevel.has(level)) nodesByLevel.set(level, [])
      nodesByLevel.get(level)!.push(node)
    })
    
    return all.map((id) => {
      const level = levels.get(id) || 0
      const nodesAtLevel = nodesByLevel.get(level) || []
      const indexAtLevel = nodesAtLevel.indexOf(id)
      const totalAtLevel = nodesAtLevel.length
      
      // Center nodes horizontally at each level
      const baseX = 400 // Center position
      const spacing = 200
      const totalWidth = (totalAtLevel - 1) * spacing
      const x = baseX - totalWidth / 2 + indexAtLevel * spacing
      const y = level * 150 + 50 // Vertical spacing between levels
      
      return {
        id, 
        position: { x, y },
        data: { label: `${id} (${statusMap.get(id) ?? 'PENDING'})` },
        style: { 
          border: '1px solid #ccc', 
          padding: 8, 
          borderRadius: 8, 
          background: colorFor(statusMap.get(id)),
          color: '#333',
          fontWeight: 500,
          fontSize: '14px'
        },
        draggable: true
      }
    })
  }, [dag, tasks])
  const edges = useMemo(() => {
    const out:any[] = []; 
    Object.entries(dag).forEach(([from, tos]) => 
      (tos as string[]).forEach(to => 
        out.push({ 
          id:`${from}-${to}`, 
          source:from, 
          target:to,
          style: { stroke: '#333', strokeWidth: 2 },
          markerEnd: {
            type: 'arrowclosed',
            color: '#333'
          }
        })
      )
    )
    return out
  }, [dag])
  return (
    <div style={{ height:'calc(100vh - 80px)', width: '100%' }}>
      <ReactFlow 
        nodes={nodes} 
        edges={edges} 
        fitView
        nodesDraggable={true}
        nodesConnectable={false}
        elementsSelectable={true}
      >
        <MiniMap 
          nodeStrokeColor="#333"
          nodeColor={(node) => colorFor(statusMap.get(node.id))}
          nodeBorderRadius={2}
          style={{ backgroundColor: '#fff', border: '1px solid #ccc' }}
        />
        <Controls 
          style={{ backgroundColor: '#fff', border: '1px solid #ccc' }}
        />
        <Background />
      </ReactFlow>
    </div>
  )
}
function colorFor(status?:string){ switch(status){ case 'READY': return '#fff9c4'; case 'RUNNING': return '#bbdefb'; case 'SUCCEEDED': return '#c8e6c9'; case 'FAILED': return '#ffcdd2'; default: return '#f5f5f5' } }
