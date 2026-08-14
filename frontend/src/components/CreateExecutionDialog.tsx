import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, type Workflow } from "@/lib/api";

export function CreateExecutionDialog({
  open,
  onOpenChange,
  defaultInput = "",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultInput?: string;
}) {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [workflowId, setWorkflowId] = useState("");
  const [userInput, setUserInput] = useState(defaultInput);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.listWorkflows().then(setWorkflows).catch(() => undefined);
  }, [open]);

  useEffect(() => {
    setUserInput(defaultInput);
  }, [defaultInput, open]);

  async function submit() {
    if (!workflowId || !userInput.trim()) return;
    setSubmitting(true);
    try {
      const res = await api.createExecution(workflowId, userInput.trim());
      toast.success("执行已创建");
      onOpenChange(false);
      navigate(`/executions/${res.execution_id}`);
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建执行</DialogTitle>
          <DialogDescription>选择工作流并描述你要完成的任务</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>工作流</Label>
            <Select value={workflowId} onValueChange={setWorkflowId}>
              <SelectTrigger>
                <SelectValue placeholder="选择一个工作流" />
              </SelectTrigger>
              <SelectContent>
                {workflows.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>任务描述</Label>
            <Textarea
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="例如：请调研 LangGraph 的最新进展"
              rows={4}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            onClick={submit}
            disabled={submitting || !workflowId || !userInput.trim()}
          >
            {submitting ? "创建中…" : "启动执行"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
