import { useEffect, useState } from "react";

export type ExecutionEvent = {
  event: string;
  [key: string]: unknown;
};

export function useExecutionWebSocket(executionId: string | undefined) {
  const [lastEvent, setLastEvent] = useState<ExecutionEvent | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!executionId) return;

    let ws: WebSocket | null = null;
    let poll: number | undefined;
    let closed = false;
    let reconnectTimer: number | undefined;

    const connect = () => {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(
        `${proto}://${window.location.host}/ws/executions/${executionId}`,
      );

      ws.onopen = () => {
        setConnected(true);
        if (poll) {
          window.clearInterval(poll);
          poll = undefined;
        }
      };

      ws.onmessage = (e) => {
        try {
          setLastEvent(JSON.parse(e.data));
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          reconnectTimer = window.setTimeout(connect, 3000);
        }
      };
    };

    connect();

    poll = window.setInterval(async () => {
      if (ws && ws.readyState === WebSocket.OPEN) return;
      try {
        const res = await fetch(`/api/executions/${executionId}`);
        if (res.ok) {
          const data = await res.json();
          setLastEvent({ event: "status", ...data });
        }
      } catch {
        // ignore polling errors
      }
    }, 2000);

    return () => {
      closed = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (poll) window.clearInterval(poll);
      ws?.close();
    };
  }, [executionId]);

  return { lastEvent, connected };
}
