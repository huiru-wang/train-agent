"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Bot } from "lucide-react";
import { getWorkspace, type Workspace } from "@/lib/api";
import { ThreePanel } from "@/components/layout/three-panel";
import { ChatPanel } from "@/components/chat/chat-panel";
import { DocumentPanel } from "@/components/document/document-panel";
import { TaskPanel } from "@/components/task/task-panel";

export default function WorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const [workspace, setWorkspace] = useState<Workspace | null>(null);

  useEffect(() => {
    getWorkspace(workspaceId)
      .then(setWorkspace)
      .catch(() => router.push("/"));
  }, [workspaceId, router]);

  if (!workspace) {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground">
        加载中...
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Workspace Header */}
      <header className="flex items-center gap-3 border-b border-border px-4 py-2.5">
        <button
          onClick={() => router.push("/")}
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft size={18} />
        </button>
        <div className="flex items-center gap-2">
          <Bot size={16} className="text-accent" />
          <span className="text-sm font-medium text-foreground">
            {workspace.name}
          </span>
        </div>
      </header>

      {/* Three-Panel Layout */}
      <div className="flex-1 overflow-hidden">
        <ThreePanel
          left={<DocumentPanel workspaceId={workspaceId} />}
          center={<ChatPanel workspaceId={workspaceId} />}
          right={<TaskPanel workspaceId={workspaceId} />}
        />
      </div>
    </div>
  );
}

