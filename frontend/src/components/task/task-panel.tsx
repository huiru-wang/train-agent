"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Package,
  Loader2,
  CheckCircle,
  Download,
  Presentation,
  FileText,
  Mic,
  MoreHorizontal,
  Trash2,
  AlertCircle,
  ChevronRight,
} from "lucide-react";
import { listTasks, deleteTask, type Task } from "@/lib/api";

interface TaskPanelProps {
  workspaceId: string;
  onNarrate?: (taskId: string, title: string) => void;
}

const TYPE_CONFIG: Record<
  string,
  { icon: typeof Presentation; label: string }
> = {
  ppt: { icon: Presentation, label: "PPT" },
  report: { icon: FileText, label: "报告" },
  narration: { icon: Mic, label: "口播稿" },
};

const STATUS_CONFIG = {
  generating: {
    icon: Loader2,
    color: "text-yellow-500",
    label: "生成中",
    animate: true,
  },
  completed: {
    icon: CheckCircle,
    color: "text-green-500",
    label: "已完成",
    animate: false,
  },
  failed: {
    icon: Package,
    color: "text-red-500",
    label: "失败",
    animate: false,
  },
  narrating: {
    icon: Loader2,
    color: "text-yellow-500",
    label: "文本生成中",
    animate: true,
  },
  tts_generating: {
    icon: Loader2,
    color: "text-blue-500",
    label: "音频生成中",
    animate: true,
  },
  tts_failed: {
    icon: AlertCircle,
    color: "text-orange-500",
    label: "音频失败",
    animate: false,
  },
} as const;

export function TaskPanel({ workspaceId, onNarrate }: TaskPanelProps) {
  const [tasks, setTasks] = useState<Task[]>([]);

  const fetchTasks = useCallback(async () => {
    try {
      const data = await listTasks(workspaceId);
      setTasks(data);
    } catch {
      console.error("Failed to load tasks");
    }
  }, [workspaceId]);

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 5000);
    return () => clearInterval(interval);
  }, [fetchTasks]);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center border-b border-border px-4 py-3">
        <h3 className="text-sm font-medium text-foreground">产出</h3>
      </div>

      {/* Task List */}
      <div className="flex-1 overflow-y-auto p-3">
        {tasks.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-center text-muted-foreground">
            <Package size={28} strokeWidth={1} />
            <p className="text-xs">
              使用 /ppt 等命令生成的产出会显示在这里
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {tasks.map((task) => (
              <TaskItemGroup
                key={task.id}
                task={task}
                workspaceId={workspaceId}
                onDeleted={fetchTasks}
                onNarrate={onNarrate}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface TaskItemGroupProps {
  task: Task;
  workspaceId: string;
  onDeleted: () => void;
  onNarrate?: (taskId: string, title: string) => void;
}

function TaskItemGroup({ task, workspaceId, onDeleted, onNarrate }: TaskItemGroupProps) {
  const [expanded, setExpanded] = useState(true);
  const prevChildCount = useRef(task.children?.length ?? 0);

  // Auto-expand when new children appear
  const childCount = task.children?.length ?? 0;
  if (childCount > prevChildCount.current) {
    prevChildCount.current = childCount;
    if (!expanded) setExpanded(true);
  }

  const hasChildren = childCount > 0;

  return (
    <div>
      <div className="flex items-start">
        {/* Expand/collapse toggle (only for tasks with children) */}
        {hasChildren ? (
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-1.5 mr-0.5 flex-shrink-0 rounded p-0.5 text-muted-foreground/60 hover:text-foreground transition-colors"
          >
            <ChevronRight
              size={12}
              className={`transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}
            />
          </button>
        ) : (
          <span className="mt-1.5 mr-0.5 w-[18px] flex-shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <TaskItem task={task} workspaceId={workspaceId} onDeleted={onDeleted} onNarrate={onNarrate} />
        </div>
      </div>
      {/* Render children (e.g. narration tasks) */}
      {hasChildren && expanded && (
        <div className="ml-7 mt-0.5 flex flex-col gap-0.5 border-l border-border/50 pl-2">
          {task.children!.map((child) => (
            <TaskItem
              key={child.id}
              task={child}
              workspaceId={workspaceId}
              onDeleted={onDeleted}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface TaskItemProps {
  task: Task;
  workspaceId: string;
  onDeleted: () => void;
  onNarrate?: (taskId: string, title: string) => void;
}

function TaskItem({ task, workspaceId, onDeleted, onNarrate }: TaskItemProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const typeConfig = TYPE_CONFIG[task.type] ?? {
    icon: Package,
    label: task.type,
  };
  const statusKey = task.status as keyof typeof STATUS_CONFIG;
  const statusConfig = STATUS_CONFIG[statusKey] ?? STATUS_CONFIG.generating;
  const TypeIcon = typeConfig.icon;
  const StatusIcon = statusConfig.icon;

  const resultData = task.result_data
    ? JSON.parse(task.result_data)
    : null;

  // Build status label with progress info
  let statusLabel: string = statusConfig.label;
  if (task.status === "tts_generating" && resultData) {
    const progress = resultData.tts_progress || 0;
    const total = resultData.slides?.length || "?";
    statusLabel = `音频生成中 ${progress}/${total}`;
  }

  const handleDownload = () => {
    if (resultData?.file_path) {
      const apiBase =
        process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
      const downloadUrl = `${apiBase}/api/files/${encodeURIComponent(resultData.file_path)}`;
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = resultData.filename || "download";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  const handleDelete = async () => {
    setMenuOpen(false);
    try {
      await deleteTask(workspaceId, task.id);
      onDeleted();
    } catch {
      console.error("Failed to delete task");
    }
  };

  // Close menu on outside click
  useEffect(() => {
    if (!menuOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  const isPptCompleted = task.type === "ppt" && task.status === "completed";

  return (
    <div className="group flex items-start gap-2.5 rounded-lg px-2.5 py-2 transition-colors hover:bg-muted/50">
      <div className="mt-0.5 flex-shrink-0">
        <TypeIcon size={15} className="text-accent/70" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <p className="truncate text-xs font-medium text-foreground">
            {task.title ?? typeConfig.label}
          </p>
          <StatusIcon
            size={12}
            className={`flex-shrink-0 ${statusConfig.color} ${
              statusConfig.animate ? "animate-spin" : ""
            }`}
          />
        </div>
        <p className="mt-0.5 text-[10px] text-muted-foreground">
          {typeConfig.label} · {statusLabel}
        </p>
        {/* TTS error hint */}
        {task.status === "tts_failed" && resultData?.tts_error && (
          <p className="mt-0.5 text-[10px] text-orange-400">
            {resultData.tts_error}
          </p>
        )}
      </div>
      <div className="flex items-center gap-0.5 mt-0.5">
        {/* Narrate button for PPT tasks */}
        {isPptCompleted && onNarrate && (
          <button
            onClick={() => onNarrate(task.id, task.title || "PPT")}
            className="flex-shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-all hover:text-accent group-hover:opacity-100"
            title="生成口播稿"
          >
            <Mic size={12} />
          </button>
        )}
        {task.status === "completed" && resultData && (
          <button
            onClick={handleDownload}
            className="flex-shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-all hover:text-accent group-hover:opacity-100"
            title="下载"
          >
            <Download size={12} />
          </button>
        )}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex-shrink-0 rounded p-1 text-muted-foreground opacity-0 transition-all hover:text-foreground group-hover:opacity-100"
            title="更多操作"
          >
            <MoreHorizontal size={12} />
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full z-50 mt-1 w-28 rounded-lg border border-border bg-[#1e1e2e] py-1 shadow-xl">
              <button
                onClick={handleDelete}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-red-400 hover:bg-muted/50"
              >
                <Trash2 size={12} />
                删除
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

