import { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  addEdge,
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Brain, GitBranch, Search, UserCheck, Zap } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";

const NODE_TYPES = [
  { type: "research", label: "Research Agent", icon: Search, color: "#3b82f6" },
  { type: "analyze", label: "Analyze Agent", icon: Brain, color: "#8b5cf6" },
  { type: "execute", label: "Execute Agent", icon: Zap, color: "#10b981" },
  { type: "condition", label: "Condition Node", icon: GitBranch, color: "#f59e0b" },
  { type: "human_approval", label: "Human Approval", icon: UserCheck, color: "#ef4444" },
];

const TOOLS = ["search_web", "query_db", "send_email"];

function WorkflowNode({ data }: NodeProps) {
  const meta = NODE_TYPES.find((n) => n.type === data.type);

  return (
    <div className="rounded-md border bg-card px-4 py-2 text-sm shadow-xs">
      <Handle type="target" position={Position.Top} />
      <div className="flex items-center gap-2 font-medium">
        {meta ? <meta.icon className="h-4 w-4" style={{ color: meta.color }} /> : null}
        {String(data.label ?? "")}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export default function WorkflowEditor() {
  const navigate = useNavigate();
  const [name, setName] = useState("未命名工作流");
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selected, setSelected] = useState<Node | null>(null);

  const nodeTypes = useMemo(() => ({ workflow: WorkflowNode }), []);

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge(connection, eds)),
    [setEdges],
  );

  function onDrop(event: React.DragEvent) {
    event.preventDefault();
    const type = event.dataTransfer.getData("application/reactflow");
    const meta = NODE_TYPES.find((n) => n.type === type);
    if (!meta) return;

    setNodes((nds) => [
      ...nds,
      {
        id: `${type}-${Date.now()}`,
        type: "workflow",
        position: { x: 120, y: 80 + nds.length * 90 },
        data: { label: meta.label, type, tools: [], condition: "" },
      },
    ]);
  }

  function dagPayload() {
    return {
      name,
      description: "",
      agent_chain: nodes.map((n) => n.id),
      dag_definition: {
        nodes: nodes.map((n) => ({
          id: n.id,
          type: n.data.type,
          label: String(n.data.label),
          system_prompt: String(n.data.system_prompt ?? ""),
          tools: (n.data.tools as string[]) ?? [],
          condition: String(n.data.condition ?? ""),
        })),
        edges: edges.map((e) => ({ source: e.source, target: e.target })),
      },
    };
  }

  async function save() {
    const wf = await api.saveWorkflow(dagPayload());
    toast.success("工作流已保存");
    localStorage.setItem("agenthub.lastWorkflowId", wf.id);
  }

  function exportJson() {
    const blob = new Blob([JSON.stringify(dagPayload(), null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name || "workflow"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function updateSelected(patch: Record<string, unknown>) {
    if (!selected) return;
    setNodes((nds) =>
      nds.map((n) =>
        n.id === selected.id ? { ...n, data: { ...n.data, ...patch } } : n,
      ),
    );
    setSelected((s) => (s ? { ...s, data: { ...s.data, ...patch } } : s));
  }

  function toggleTool(tool: string) {
    const current = ((selected?.data.tools as string[]) ?? []).slice();
    const idx = current.indexOf(tool);
    if (idx >= 0) current.splice(idx, 1);
    else current.push(tool);
    updateSelected({ tools: current });
  }

  return (
    <div className="flex flex-col gap-4 lg:h-[calc(100vh-7rem)] lg:min-h-[560px] lg:flex-row">
      <Card className="w-full shrink-0 shadow-sm lg:w-56">
        <CardHeader>
          <CardTitle className="type-label">节点库</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-2 overflow-x-auto pb-2 lg:flex-col lg:space-y-2">
          {NODE_TYPES.map((n) => (
            <div
              key={n.type}
              draggable
              onDragStart={(e) =>
                e.dataTransfer.setData("application/reactflow", n.type)
              }
              className="flex shrink-0 cursor-grab items-center gap-2 rounded-md border bg-card p-2 text-sm transition-all duration-150 hover:bg-muted/50 active:scale-[0.98] lg:w-full"
            >
              <n.icon className="h-4 w-4" style={{ color: n.color }} />
              {n.label}
            </div>
          ))}
        </CardContent>
      </Card>

      <div
        className="h-[60vh] min-h-[360px] w-full min-w-0 flex-1 overflow-hidden rounded-lg border bg-background lg:h-auto lg:min-h-0"
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, node) => setSelected(node)}
          nodeTypes={nodeTypes}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>

      <Card className="w-full shrink-0 shadow-sm lg:w-80">
        <CardHeader>
          <CardTitle className="type-label">属性</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label>工作流名称</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>

          {selected ? (
            <>
              <div className="space-y-2">
                <Label>节点名称</Label>
                <Input
                  value={String(selected.data.label ?? "")}
                  onChange={(e) => updateSelected({ label: e.target.value })}
                />
              </div>

              <div className="space-y-2">
                <Label>System Prompt</Label>
                <Textarea
                  value={String(selected.data.system_prompt ?? "")}
                  onChange={(e) =>
                    updateSelected({ system_prompt: e.target.value })
                  }
                />
              </div>

              {selected.data.type === "condition" ? (
                <div className="space-y-2">
                  <Label>条件表达式</Label>
                  <Input
                    placeholder="例如 len(final_output) > 100"
                    value={String(selected.data.condition ?? "")}
                    onChange={(e) =>
                      updateSelected({ condition: e.target.value })
                    }
                  />
                </div>
              ) : (
                <div className="space-y-2">
                  <Label>关联工具</Label>
                  {TOOLS.map((tool) => (
                    <label
                      key={tool}
                      className="flex items-center gap-2 text-sm text-muted-foreground"
                    >
                      <input
                        type="checkbox"
                        className="accent-primary"
                        checked={((selected.data.tools as string[]) ?? []).includes(
                          tool,
                        )}
                        onChange={() => toggleTool(tool)}
                      />
                      {tool}
                    </label>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              点击画布节点查看配置
            </p>
          )}

          <div className="flex gap-2">
            <Button className="flex-1" onClick={save}>
              保存工作流
            </Button>
            <Button variant="outline" onClick={exportJson}>
              导出
            </Button>
          </div>
          <Button
            variant="secondary"
            className="w-full"
            onClick={() => navigate("/executions")}
          >
            去执行
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
