"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Plus, Bot } from "lucide-react";
import { getUserId } from "@/lib/user";
import {
  ApiError,
  listWorkspaces,
  createWorkspace,
  deleteWorkspace,
  type Workspace,
} from "@/lib/api";
import { WorkspaceCard } from "@/components/workspace/workspace-card";
import { CreateDialog } from "@/components/workspace/create-dialog";

export default function Home() {
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null);

  const fetchWorkspaces = useCallback(async () => {
    try {
      const userId = getUserId();
      const data = await listWorkspaces(userId);
      setWorkspaces(data);
    } catch {
      console.error("Failed to load workspaces");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  const handleCreate = async (name: string) => {
    const userId = getUserId();
    try {
      await createWorkspace(userId, name);
      await fetchWorkspaces();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        throw new Error("工作区名称已存在");
      }
      throw err;
    }
  };

  const handleDelete = (id: string) => {
    const ws = workspaces.find((w) => w.id === id) ?? null;
    setDeleteTarget(ws);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const id = deleteTarget.id;
    setDeleteTarget(null);
    await deleteWorkspace(id);
    fetchWorkspaces();
  };

  const handleOpen = (id: string) => {
    router.push(`/workspace/${id}`);
  };

  return (
    <div className="flex flex-1 flex-col">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border px-8 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/20 text-accent">
            <Bot size={18} />
          </div>
          <h1 className="text-lg font-semibold text-foreground">
            Train Agent
          </h1>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1 px-8 py-8">
        <div className="mx-auto max-w-4xl">
          <div className="mb-6 flex items-center justify-between">
            <h2 className="text-xl font-semibold text-foreground">工作区</h2>
            <button
              onClick={() => setDialogOpen(true)}
              className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground transition-colors hover:bg-accent/90"
            >
              <Plus size={15} />
              新建工作区
            </button>
          </div>

          {loading ? (
            <div className="py-20 text-center text-muted-foreground">
              加载中...
            </div>
          ) : workspaces.length === 0 ? (
            <div className="flex flex-col items-center gap-4 py-20 text-muted-foreground">
              <Bot size={48} strokeWidth={1} />
              <p>还没有工作区，创建一个开始吧</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {workspaces.map((workspace) => (
                <WorkspaceCard
                  key={workspace.id}
                  workspace={workspace}
                  onOpen={handleOpen}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </div>
      </main>

      <CreateDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreate={handleCreate}
      />

      {/* Delete workspace confirmation dialog */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="mx-4 w-full max-w-sm rounded-2xl border border-border bg-background p-5 shadow-2xl">
            <h3 className="text-sm font-semibold text-foreground">
              删除工作区「{deleteTarget.name}」？
            </h3>
            <div className="mt-2 space-y-1.5 text-xs text-muted-foreground">
              <p>
                工作区下的知识库和产出文件将被永久删除，
                <span className="text-red-400">此操作不可撤销</span>。
              </p>
              <p className="text-muted-foreground/80">已保存的 PPT 风格模版不受影响。</p>
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setDeleteTarget(null)}
                className="rounded-lg px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                取消
              </button>
              <button
                onClick={confirmDelete}
                className="rounded-lg bg-red-500/20 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/30"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
