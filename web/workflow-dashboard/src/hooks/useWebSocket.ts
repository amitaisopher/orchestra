import { useEffect, useRef, useState } from 'react';

interface WorkflowUpdate {
  workflow_id: string;
  status: string;
  tasks: Array<{
    taskId: string;
    status: string;
    type: string;
  }>;
}

interface WebSocketMessage {
  type: 'workflow_update';
  workflow_id: string;
  data: WorkflowUpdate;
}

export function useWebSocket(url: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [workflowUpdates, setWorkflowUpdates] = useState<WorkflowUpdate[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = () => {
    if (!url || wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        // Clear any pending reconnect attempts
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          
          if (message.type === 'workflow_update') {
            console.log('Received workflow update:', message.data);
            setWorkflowUpdates((prev: WorkflowUpdate[]) => {
              // Replace existing update for same workflow or add new one
              const filtered = prev.filter((update: WorkflowUpdate) => 
                update.workflow_id !== message.workflow_id
              );
              return [...filtered, message.data];
            });
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      ws.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        setIsConnected(false);
        wsRef.current = null;

        // Attempt to reconnect after a delay if not a manual close
        if (event.code !== 1000) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('Attempting to reconnect...');
            connect();
          }, 3000) as unknown as number;
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setIsConnected(false);
      };

    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
    }
  };

  const disconnect = () => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    if (wsRef.current) {
      wsRef.current.close(1000, 'Manual disconnect');
      wsRef.current = null;
    }
    setIsConnected(false);
  };

  // Get the latest update for a specific workflow
  const getWorkflowUpdate = (workflowId: string): WorkflowUpdate | undefined => {
    return workflowUpdates.find((update: WorkflowUpdate) => update.workflow_id === workflowId);
  };

  // Clear updates for a specific workflow
  const clearWorkflowUpdate = (workflowId: string) => {
    setWorkflowUpdates((prev: WorkflowUpdate[]) => 
      prev.filter((update: WorkflowUpdate) => update.workflow_id !== workflowId)
    );
  };

  useEffect(() => {
    if (url) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [url]);

  return {
    isConnected,
    workflowUpdates,
    connect,
    disconnect,
    getWorkflowUpdate,
    clearWorkflowUpdate,
  };
}