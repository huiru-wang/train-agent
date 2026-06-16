"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useStream } from "@langchain/react";
import { updateWorkspaceThreadId, getWorkspace, listThreadMessages, type ThreadMessage } from "@/lib/api";

const LANGGRAPH_API_URL =
  process.env.NEXT_PUBLIC_LANGGRAPH_API_URL || "http://localhost:2024";
// Number of *turns* to load per page (a turn = 1 human message + all following AI/tool messages)
const MESSAGE_HISTORY_LIMIT = 3;

// --- External command (for programmatic pill injection from parent components) ---

export interface ExternalCommand {
  command: string;
  label: string;
  icon: ReactNode;
  subtitle?: string;
  metadata?: Record<string, string>;
}

// --- Stream context ---

interface StreamContextValue {
  messages: any[];
  isLoading: boolean;
  interrupt: { value?: unknown } | undefined;
  submit: (content: string) => void;
  stop: () => void;
  error: Error | null;
  pendingMessage: string | null;
  loadOlderMessages: () => Promise<void>;
  hasOlderMessages: boolean;
  isLoadingOlderMessages: boolean;
  externalCommand: ExternalCommand | null;
  onExternalCommandConsumed?: () => void;
}

const StreamContext = createContext<StreamContextValue>({
  messages: [],
  isLoading: false,
  interrupt: undefined,
  submit: () => { },
  stop: () => { },
  error: null,
  pendingMessage: null,
  loadOlderMessages: async () => { },
  hasOlderMessages: false,
  isLoadingOlderMessages: false,
  externalCommand: null,
});

export function useStreamContext() {
  return useContext(StreamContext);
}

// --- Resume context (for interrupt forms) ---

const ResumeContext = createContext<
  (values: Record<string, string | string[]>) => Promise<void>
>(async () => { });
export function useResume() {
  return useContext(ResumeContext);
}

// --- Assistant ---

interface AssistantProps {
  workspaceId: string;
  pptStyle?: string;
  currentPptTaskId?: string;
  onPptTaskIdConsumed?: () => void;
  externalCommand?: ExternalCommand | null;
  onExternalCommandConsumed?: () => void;
  children: ReactNode;
}

export function Assistant({ workspaceId, pptStyle, currentPptTaskId, onPptTaskIdConsumed, externalCommand, onExternalCommandConsumed, children }: AssistantProps) {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [historyMessages, setHistoryMessages] = useState<any[]>([]);
  const [historyNextCursor, setHistoryNextCursor] = useState<number | null>(null);
  const [isLoadingOlderMessages, setIsLoadingOlderMessages] = useState(false);
  const [liveMessages, setLiveMessages] = useState<any[]>([]);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const prevMessageCount = useRef(0);
  const streamBaselineKeys = useRef<Set<string>>(new Set());
  const wasLoading = useRef(false);

  const loadHistoryMessages = useCallback(async (targetThreadId: string) => {
    const page = await listThreadMessages(targetThreadId, { limit: MESSAGE_HISTORY_LIMIT });
    setHistoryMessages(page.messages.map(toLangGraphMessage).filter((message) => !isSummarizationMessage(message)));
    setHistoryNextCursor(page.next_cursor);
  }, []);

  const loadOlderMessages = useCallback(async () => {
    if (!threadId || !historyNextCursor || isLoadingOlderMessages) return;

    setIsLoadingOlderMessages(true);
    try {
      const page = await listThreadMessages(threadId, {
        limit: MESSAGE_HISTORY_LIMIT,
        before: historyNextCursor,
      });
      const olderMessages = page.messages
        .map(toLangGraphMessage)
        .filter((message) => !isSummarizationMessage(message));
      setHistoryMessages((current) => mergeMessages(olderMessages, current));
      setHistoryNextCursor(page.next_cursor);
    } finally {
      setIsLoadingOlderMessages(false);
    }
  }, [historyNextCursor, isLoadingOlderMessages, threadId]);

  // Load threadId from server
  useEffect(() => {
    getWorkspace(workspaceId)
      .then((ws) => {
        if (ws.thread_id) setThreadId(ws.thread_id);
      })
      .catch(() => { });
  }, [workspaceId]);

  useEffect(() => {
    if (!threadId) {
      setHistoryMessages([]);
      setHistoryNextCursor(null);
      setLiveMessages([]);
      streamBaselineKeys.current = new Set();
      return;
    }
    let cancelled = false;
    loadHistoryMessages(threadId)
      .then(() => {
        if (!cancelled) {
          setLiveMessages([]);
          streamBaselineKeys.current = new Set();
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHistoryMessages([]);
          setHistoryNextCursor(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [threadId, loadHistoryMessages]);

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
      updateWorkspaceThreadId(workspaceId, stream.threadId).catch(() => { });
    }
  }, [stream.threadId, workspaceId, threadId]);

  // Clear pending message once server echoes back
  useEffect(() => {
    if (stream.messages.length > prevMessageCount.current && pendingMessage) {
      setPendingMessage(null);
    }
    prevMessageCount.current = stream.messages.length;
  }, [stream.messages.length, pendingMessage]);

  useEffect(() => {
    const streamMessages = stream.messages ?? [];
    if (pendingMessage || stream.isLoading || liveMessages.length > 0) {
      const baseline = streamBaselineKeys.current;
      setLiveMessages(
        streamMessages.filter((message) => {
          return !baseline.has(messageKey(message)) && !isSummarizationMessage(message);
        }),
      );
    } else {
      streamBaselineKeys.current = new Set(streamMessages.map(messageKey));
    }
  }, [stream.messages, stream.isLoading, pendingMessage, liveMessages.length]);

  useEffect(() => {
    const justFinished = wasLoading.current && !stream.isLoading;
    wasLoading.current = stream.isLoading;
    if (!justFinished || !threadId) return;

    loadHistoryMessages(threadId)
      .then(() => {
        setLiveMessages([]);
        streamBaselineKeys.current = new Set((stream.messages ?? []).map(messageKey));
      })
      .catch(() => { });
  }, [stream.isLoading, stream.messages, threadId, loadHistoryMessages]);

  const streamRef = useRef(stream);
  streamRef.current = stream;

  // Wrapped submit — slash command is now encoded directly in content
  const handleSubmit = (content: string) => {
    streamBaselineKeys.current = new Set((streamRef.current.messages ?? []).map(messageKey));
    setLiveMessages([]);
    setPendingMessage(content);
    streamRef.current.submit(
      {
        messages: [{ type: "human", content }],
        workspace_id: workspaceId,
        ppt_style: pptStyle || "",
        current_ppt_task_id: currentPptTaskId || "",
      },
      { config: { recursion_limit: 30 } },
    );
    // Clear the narrate task ID after submitting
    if (currentPptTaskId) {
      onPptTaskIdConsumed?.();
    }
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
        messages: mergeMessages(historyMessages, liveMessages),
        isLoading: stream.isLoading,
        interrupt: stream.interrupt,
        submit: handleSubmit,
        stop: handleStop,
        error: (stream.error as Error) ?? null,
        pendingMessage,
        loadOlderMessages,
        hasOlderMessages: historyNextCursor !== null,
        isLoadingOlderMessages,
        externalCommand: externalCommand ?? null,
        onExternalCommandConsumed,
      }}
    >
      <ResumeContext.Provider value={handleResume}>
        {children}
      </ResumeContext.Provider>
    </StreamContext.Provider>
  );
}

function toLangGraphMessage(message: ThreadMessage) {
  return {
    id: message.message_id,
    type: message.type || message.role,
    content: message.content,
    tool_calls: message.tool_calls ?? [],
    tool_call_id: message.tool_call_id ?? undefined,
    name: message.name ?? undefined,
    additional_kwargs: message.additional_kwargs ?? {},
    response_metadata: message.response_metadata ?? {},
  };
}

function messageKey(message: any): string {
  const type = message?._getType?.() || message?.type || message?.role || "message";
  const id = message?.id || message?.message_id;
  if (id) return `${type}:${id}`;
  return `${type}:${JSON.stringify(message?.content ?? "")}`;
}

function isSummarizationMessage(message: any): boolean {
  const additionalKwargs = message?.additional_kwargs ?? message?.kwargs?.additional_kwargs;
  return additionalKwargs?.lc_source === "summarization";
}

function mergeMessages(history: any[], live: any[]) {
  const merged = [...history];
  const seen = new Set(history.map(messageKey));
  for (const message of live) {
    const key = messageKey(message);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(message);
  }
  return merged;
}
