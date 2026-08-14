import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

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
          <p>API 文档：http://localhost:8000/docs</p>
        </CardContent>
      </Card>
    </div>
  );
}
