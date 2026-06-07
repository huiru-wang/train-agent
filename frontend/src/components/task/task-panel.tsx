"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Package,
  Loader2,
  CheckCircle,
  Download,
  Presentation,
  FileText,
  MoreHorizontal,
  Trash2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { listTasks, deleteTask, type Task } from "@/lib/api";

interface TaskPanelProps {
  workspaceId: string;
  collapsed?: boolean;
  onToggle?: () => void;
}

const TYPE_CONFIG: Record<
  string,
  { icon: typeof Presentation; label: string }
> = {
  ppt: { icon: Presentation, label: "PPT" },
  report: { icon: FileText, label: "报告" },
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
} as const;

export function TaskPanel({ workspaceId, collapsed, onToggle }: TaskPanelProps) {
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
      <div className="flex items-center border-b border-border px-4 py-3 gap-2">
        {onToggle && (
          <button
            type="button"
            onClick={onToggle}
            className="flex items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label={collapsed ? "展开产出" : "收起产出"}
            title={collapsed ? "展开产出" : "收起产出"}
          >
            {collapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
          </button>
        )}
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
              <TaskItem
                key={task.id}
                task={task}
                workspaceId={workspaceId}
                onDeleted={fetchTasks}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface TaskItemProps {
  task: Task;
  workspaceId: string;
  onDeleted: () => void;
}

function TaskItem({ task, workspaceId, onDeleted }: TaskItemProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const typeConfig = TYPE_CONFIG[task.type] ?? {
    icon: Package,
    label: task.type,
  };
  const statusConfig =
    STATUS_CONFIG[task.status as keyof typeof STATUS_CONFIG] ??
    STATUS_CONFIG.generating;
  const TypeIcon = typeConfig.icon;
  const StatusIcon = statusConfig.icon;

  const resultData = task.result_data
    ? JSON.parse(task.result_data)
    : null;

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
          {typeConfig.label} · {statusConfig.label}
        </p>
      </div>
      <div className="flex items-center gap-0.5 mt-0.5">
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
