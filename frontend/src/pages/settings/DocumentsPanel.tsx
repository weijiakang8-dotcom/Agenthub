import { useEffect, useRef, useState } from "react";
import { FileText, Search, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, type DocumentItem } from "@/lib/api";

export default function DocumentsPanel() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DocumentItem[] | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    try {
      setDocuments(await api.listDocuments());
    } catch (err) {
      toast.error(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function upload(file: File | undefined) {
    if (!file) return;
    try {
      await api.uploadDocument(file);
      toast.success("文档已上传并完成向量化");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function create() {
    if (!name.trim() || !content.trim()) {
      toast.error("请填写文档名称和内容");
      return;
    }
    try {
      await api.createDocument({ name: name.trim(), content });
      toast.success("文档已创建");
      setName("");
      setContent("");
      await load();
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteDocument(id);
      toast.success("文档已删除");
      await load();
      if (results) setResults(results.filter((r) => r.id !== id));
    } catch (err) {
      toast.error(String(err));
    }
  }

  async function search() {
    if (!query.trim()) return;
    try {
      setResults(await api.searchDocuments(query.trim()));
    } catch (err) {
      toast.error(String(err));
    }
  }

  return (
    <div className="space-y-5">
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">上传 / 添加知识</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.md,.markdown,.pdf"
              className="hidden"
              onChange={(e) => upload(e.target.files?.[0])}
            />
            <Button variant="outline" onClick={() => fileRef.current?.click()}>
              <Upload className="mr-2 h-4 w-4" />
              上传文件
            </Button>
            <p className="text-xs text-muted-foreground">
              支持 TXT、Markdown、PDF，上传后自动向量化。
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-[240px_1fr]">
            <div className="space-y-2">
              <Label>文档名称</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="产品说明.md"
              />
            </div>
            <div className="space-y-2">
              <Label>内容</Label>
              <Textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="粘贴需要注入 Agent 上下文的知识内容"
                className="min-h-28"
              />
            </div>
          </div>
          <Button onClick={create}>保存文档</Button>
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">语义检索</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") search();
              }}
              placeholder="输入问题，在知识库中检索"
            />
            <Button variant="outline" onClick={search}>
              <Search className="mr-2 h-4 w-4" />
              检索
            </Button>
          </div>
          {results && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">
                找到 {results.length} 条相关文档
              </p>
              {results.map((doc) => (
                <div key={doc.id} className="rounded-lg border bg-muted/30 p-3">
                  <p className="text-sm font-medium">{doc.name}</p>
                  <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">
                    {doc.content}
                  </p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="type-h3">知识库文档</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-32 w-full" />
          ) : documents.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="暂无文档"
              description="上传或粘贴文档，让 Agent 具备私有知识检索能力。"
            />
          ) : (
            <div className="divide-y">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className="flex items-start justify-between gap-3 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{doc.name}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                      {doc.content}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => remove(doc.id)}
                  >
                    <Trash2 className="h-4 w-4 text-muted-foreground" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
