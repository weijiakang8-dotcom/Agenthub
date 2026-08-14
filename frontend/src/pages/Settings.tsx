import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Link } from "react-router-dom";

export default function Settings() {
  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-semibold tracking-tight">设置</h2>
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>关于 AgentHub</CardTitle>
          <CardDescription>多智能体协作平台</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          <p>版本：0.1.0</p>
          <p>协议：MIT</p>
          <Separator className="my-3" />
          <p>
            API 文档：
            <a
              className="text-primary underline-offset-4 hover:underline"
              href={`${window.location.protocol}//${window.location.hostname}:8000/docs`}
              target="_blank"
              rel="noreferrer"
            >
              打开 Swagger 文档
            </a>
          </p>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>管理工具</CardTitle>
          <CardDescription>工作流与执行的高级管理入口</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm">
          <Link className="text-primary underline-offset-4 hover:underline" to="/executions">
            执行记录
          </Link>
          <Link className="text-primary underline-offset-4 hover:underline" to="/workflows">
            工作流
          </Link>
          <Link className="text-primary underline-offset-4 hover:underline" to="/workflows/editor">
            工作流编辑器
          </Link>
          <Link className="text-primary underline-offset-4 hover:underline" to="/alerts">
            告警中心
          </Link>
          <Link className="text-primary underline-offset-4 hover:underline" to="/quality">
            质量看板
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
