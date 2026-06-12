"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useStream } from "@langchain/react";
import { updateWorkspaceThreadId, getWorkspace } from "@/lib/api";

const LANGGRAPH_API_URL =
  process.env.NEXT_PUBLIC_LANGGRAPH_API_URL || "http://localhost:2024";

// --- Stream context ---

interface StreamContextValue {
  messages: any[];
  isLoading: boolean;
  interrupt: { value?: unknown } | undefined;
  submit: (content: string) => void;
  stop: () => void;
  error: Error | null;
  pendingMessage: string | null;
}

const StreamContext = createContext<StreamContextValue>({
  messages: [],
  isLoading: false,
  interrupt: undefined,
  submit: () => {},
  stop: () => {},
  error: null,
  pendingMessage: null,
});

export function useStreamContext() {
  return useContext(StreamContext);
}

// --- Resume context (for interrupt forms) ---

const ResumeContext = createContext<(values: Record<string, string | string[]>) => void>(() => {});
export function useResume() {
  return useContext(ResumeContext);
}

// --- Assistant ---

interface AssistantProps {
  workspaceId: string;
  children: ReactNode;
}

export function Assistant({ workspaceId, children }: AssistantProps) {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const prevMessageCount = useRef(0);

  // Load threadId from server
  useEffect(() => {
    getWorkspace(workspaceId)
      .then((ws) => {
        if (ws.thread_id) setThreadId(ws.thread_id);
      })
      .catch(() => {});
  }, [workspaceId]);

  const stream = useStream({
    apiUrl: LANGGRAPH_API_URL,
    assistantId: "train_agent",
    threadId,
  });

  // Debug: log stream state changes
  useEffect(() => {
    console.log("[Assistant] stream state:", {
      threadId: stream.threadId,
      messagesCount: stream.messages?.length,
      isLoading: stream.isLoading,
      error: stream.error,
      interrupt: stream.interrupt,
    });
  }, [stream.threadId, stream.messages?.length, stream.isLoading, stream.error, stream.interrupt]);

  // Auto-recover from stale threadId
  useEffect(() => {
    if (stream.error) {
      console.error("[Assistant] stream error:", stream.error);
      const msg =
        stream.error instanceof Error
          ? stream.error.message
          : String(stream.error);
      if (
        msg.includes("404") ||
        msg.includes("not found") ||
        msg.includes("Thread")
      ) {
        setThreadId(null);
      }
    }
  }, [stream.error]);

  // Persist new threadId
  useEffect(() => {
    if (stream.threadId && stream.threadId !== threadId) {
      setThreadId(stream.threadId);
      updateWorkspaceThreadId(workspaceId, stream.threadId).catch(() => {});
    }
  }, [stream.threadId, workspaceId, threadId]);

  // Clear pending message once server echoes back
  useEffect(() => {
    if (stream.messages.length > prevMessageCount.current && pendingMessage) {
      setPendingMessage(null);
    }
    prevMessageCount.current = stream.messages.length;
  }, [stream.messages.length, pendingMessage]);

  const streamRef = useRef(stream);
  streamRef.current = stream;

  // Wrapped submit — slash command is now encoded directly in content
  const handleSubmit = (content: string) => {
    setPendingMessage(content);
    streamRef.current.submit(
      {
        messages: [{ type: "human", content }],
        workspace_id: workspaceId,
      },
      { config: { recursion_limit: 30 } },
    );
  };

  const handleResume = (values: Record<string, string | string[]>) => {
    // useStream.submit 在无 active streaming session 时不抛异常，而是把错误写入
    // stream.error state，try/catch 无法捕获，重启后必然失败。
    // 直接调用 LangGraph REST API 创建 resume run，消费 SSE 流，
    // 流结束后重置 threadId 强制 useStream 重新 hydrate 以拉取最新消息。
    const currentThreadId = streamRef.current.threadId ?? threadId;
    if (!currentThreadId) {
      console.error("[handleResume] no threadId available, cannot resume");
      return;
    }

    fetch(`${LANGGRAPH_API_URL}/threads/${currentThreadId}/runs/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        assistant_id: "train_agent",
        command: { resume: values },
        config: { recursion_limit: 30 },
        stream_mode: ["messages-tuple", "updates"],
      }),
    })
      .then(async (res) => {
        if (!res.ok) {
          console.error("[handleResume] resume run failed:", res.status, res.statusText);
          return;
        }
        // 消费 SSE 流直到结束，确保 run 完全执行完毕后再 hydrate
        const reader = res.body?.getReader();
        if (reader) {
          while (true) {
            const { done } = await reader.read();
            if (done) break;
          }
        }
        // 重置 threadId 触发 useStream 重新 hydrate，拉取最新 messages
        setThreadId(null);
        setTimeout(() => setThreadId(currentThreadId), 50);
      })
      .catch((err) => {
        console.error("[handleResume] REST API request error:", err);
      });
  };

  const handleStop = () => {
    streamRef.current.stop();
  };

  return (
    <StreamContext.Provider
      value={{
        messages: stream.messages ?? [],
        isLoading: stream.isLoading,
        interrupt: stream.interrupt,
        submit: handleSubmit,
        stop: handleStop,
        error: (stream.error as Error) ?? null,
        pendingMessage,
      }}
    >
      <ResumeContext.Provider value={handleResume}>
        {children}
      </ResumeContext.Provider>
    </StreamContext.Provider>
  );
}
