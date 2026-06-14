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

const ResumeContext = createContext<
  (values: Record<string, string | string[]>) => Promise<void>
>(async () => {});
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

  const handleResume = async (values: Record<string, string | string[]>) => {
    await streamRef.current.respond(values);
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
