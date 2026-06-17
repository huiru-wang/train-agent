"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Bot, Mic } from "lucide-react";
import { getWorkspace, type Workspace, type Task } from "@/lib/api";
import { ThreePanel } from "@/components/layout/three-panel";
import { ChatPanel } from "@/components/chat/chat-panel";
import { DocumentPanel } from "@/components/document/document-panel";
import { TaskPanel } from "@/components/task/task-panel";
import { ConfigPanel } from "@/components/config/config-panel";
import { PPTPlayerDialog } from "@/components/player/ppt-player-dialog";
import { PPTPreviewDialog } from "@/components/player/ppt-preview-dialog";
import type { ExternalCommand } from "@/components/chat/assistant";

export default function WorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params.id as string;
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [pptStyle, setPptStyle] = useState("swiss-modern");
  const [voiceId, setVoiceId] = useState("Cherry");
  const [currentPptTaskId, setCurrentPptTaskId] = useState("");
  const [externalCommand, setExternalCommand] = useState<ExternalCommand | null>(null);
  const [playerData, setPlayerData] = useState<{ narrationTask: Task; pptTask: Task } | null>(null);
  const [previewTask, setPreviewTask] = useState<Task | null>(null);

  useEffect(() => {
    getWorkspace(workspaceId)
      .then((ws) => {
        setWorkspace(ws);
        // Read config from ext_data
        const ext = ws.ext_data ?? {};
        if (ext.ppt_style) setPptStyle(ext.ppt_style as string);
        if (ext.voice_id) setVoiceId(ext.voice_id as string);
      })
      .catch(() => router.push("/"));
  }, [workspaceId, router]);

  const handleConfigChange = useCallback((key: string, value: string) => {
    if (key === "ppt_style") setPptStyle(value);
    if (key === "voice_id") setVoiceId(value);
  }, []);

  const handleNarrate = useCallback((taskId: string, title: string) => {
    setCurrentPptTaskId(taskId);
    setExternalCommand({
      command: "/narrate",
      label: "生成口播稿",
      icon: <Mic size={14} />,
      subtitle: title,
      metadata: { pptTaskId: taskId },
    });
  }, []);

  const handlePptTaskIdConsumed = useCallback(() => {
    setCurrentPptTaskId("");
  }, []);

  const handleExternalCommandConsumed = useCallback(() => {
    setExternalCommand(null);
  }, []);

  const handlePlayNarration = useCallback((narrationTask: Task, pptTask: Task) => {
    setPlayerData({ narrationTask, pptTask });
  }, []);

  const handlePreview = useCallback((task: Task) => {
    setPreviewTask(task);
  }, []);

  if (!workspace) {
    return (
      <div className="flex h-screen items-center justify-center text-muted-foreground">
        加载中...
      </div>
    );
  }

  const rightPanel = (
    <div className="flex h-full flex-col">
      <ConfigPanel
        workspaceId={workspaceId}
        pptStyle={pptStyle}
        voiceId={voiceId}
        onConfigChange={handleConfigChange}
      />
      <div className="min-h-0 flex-1 overflow-hidden">
        <TaskPanel workspaceId={workspaceId} onNarrate={handleNarrate} onPlayNarration={handlePlayNarration} onPreview={handlePreview} />
      </div>
    </div>
  );

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
          center={<ChatPanel workspaceId={workspaceId} pptStyle={pptStyle} voiceId={voiceId} currentPptTaskId={currentPptTaskId} onPptTaskIdConsumed={handlePptTaskIdConsumed} externalCommand={externalCommand} onExternalCommandConsumed={handleExternalCommandConsumed} />}
          right={rightPanel}
          rightCollapsed={rightCollapsed}
          onRightToggle={() => setRightCollapsed((v) => !v)}
        />
      </div>

      {/* PPT Player Dialog */}
      {playerData && (
        <PPTPlayerDialog
          workspaceId={workspaceId}
          narrationTask={playerData.narrationTask}
          pptTask={playerData.pptTask}
          onClose={() => setPlayerData(null)}
        />
      )}

      {/* PPT Preview Dialog */}
      {previewTask && (
        <PPTPreviewDialog
          workspaceId={workspaceId}
          pptTask={previewTask}
          onClose={() => setPreviewTask(null)}
        />
      )}
    </div>
  );
}

