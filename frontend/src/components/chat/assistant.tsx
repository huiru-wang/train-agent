"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
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
  const summarizedIds = useRef<Set<string>>(new Set());

  const loadHistoryMessages = useCallback(async (targetThreadId: string) => {
    const page = await listThreadMessages(targetThreadId, { limit: MESSAGE_HISTORY_LIMIT });
    setHistoryMessages(page.messages.map(toLangGraphMessage).filter((message) => !isHiddenMessage(message)));
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
        .filter((message) => !isHiddenMessage(message));
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
      return;
    }
    let cancelled = false;
    loadHistoryMessages(threadId).catch(() => {
      if (!cancelled) {
        setHistoryMessages([]);
        setHistoryNextCursor(null);
      }
    });
    return () => { cancelled = true; };
  }, [threadId, loadHistoryMessages]);

  // Stable callbacks via refs — prevents useStream from seeing new references each render
  const threadIdRef = useRef(threadId);
  threadIdRef.current = threadId;
  const workspaceIdRef = useRef(workspaceId);
  workspaceIdRef.current = workspaceId;

  const handleThreadId = useCallback((newThreadId: string) => {
    if (newThreadId !== threadIdRef.current) {
      setThreadId(newThreadId);
      updateWorkspaceThreadId(workspaceIdRef.current, newThreadId).catch(() => { });
    }
  }, []);

  // Snapshot of stream messages for summarization diff (updated during render)
  const streamMessagesSnapshotRef = useRef<any[]>([]);

  const handleUpdateEvent = useCallback((data: unknown) => {
    const sumMsgs = getSummarizationMessages(data);
    if (!sumMsgs || sumMsgs.length < 2) return;

    for (const m of sumMsgs) {
      if (m.name === "summary" && m.type === "human") {
        summarizedIds.current.add(m.id ?? "");
      }
    }

    const firstRetained = sumMsgs
      .filter((m: any) => m.type !== "remove")
      .filter((m: any) => !isHiddenMessage(m))
      .map(messageIdentity)
      .find(Boolean);

    const current = [...streamMessagesSnapshotRef.current];
    const moved: any[] = [];
    for (const m of current) {
      if (firstRetained && messageIdentity(m) === firstRetained) break;
      if (!summarizedIds.current.has(m.id ?? "")) {
        moved.push(m);
      }
    }
    if (moved.length > 0) {
      setHistoryMessages((prev) => mergeMessages(prev, moved));
    }
  }, []);

  const stream = useStream({
    apiUrl: LANGGRAPH_API_URL,
    assistantId: "train_agent",
    threadId,
    onThreadId: handleThreadId,
    onUpdateEvent: handleUpdateEvent,
  });

  // Keep snapshot ref in sync (used by handleUpdateEvent callback)
  if (stream.messages.length >= streamMessagesSnapshotRef.current.length) {
    streamMessagesSnapshotRef.current = stream.messages;
  }

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

  // --- Derived: live messages (computed, NOT state — breaks the infinite loop) ---
  //
  // ROOT CAUSE: stream.messages is a getter that returns a NEW array on every
  // render. Using it as a useEffect dependency causes effect → setState →
  // re-render → effect → ... → "Maximum update depth exceeded".
  //
  // FIX: Use useMemo with primitive/stable dependency keys instead of the
  // stream.messages reference. The dep key captures:
  //   1. stream.messages.length — changes when a new message arrives
  //   2. last message content — changes on every streaming token
  //   3. stream.isLoading — changes when stream starts/ends
  //   4. historyMessages — changes when history is (re)loaded
  const liveMessages = useMemo(() => {
    const sm = stream.messages ?? [];
    const historyKeys = new Set(historyMessages.map(messageKey));
    return sm.filter(
      (m: any) => !historyKeys.has(messageKey(m)) && !isHiddenMessage(m),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    stream.messages.length,
    stream.messages.length > 0
      ? JSON.stringify((stream.messages[stream.messages.length - 1] as any)?.content ?? "").slice(0, 200)
      : "",
    stream.isLoading,
    historyMessages,
  ]);

  // Merge history + live for display
  const allMessages = useMemo(() => {
    return mergeMessages(historyMessages, liveMessages);
  }, [historyMessages, liveMessages]);

  const streamRef = useRef(stream);
  streamRef.current = stream;

  const handleSubmit = (content: string) => {
    streamRef.current.submit(
      {
        messages: [{ type: "human", content }],
        workspace_id: workspaceId,
        ppt_style: pptStyle || "",
        current_ppt_task_id: currentPptTaskId || "",
      },
      { config: { recursion_limit: 30 } },
    );
    if (currentPptTaskId) {
      onPptTaskIdConsumed?.();
    }
  };

  const handleResume = async (values: Record<string, string | string[]>) => {
    await streamRef.current.submit(null, { command: { resume: values } });
  };

  return (
    <StreamContext.Provider
      value={{
        messages: allMessages,
        isLoading: stream.isLoading,
        interrupt: stream.interrupt,
        submit: handleSubmit,
        stop: () => streamRef.current.stop(),
        error: stream.error != null ? new Error(String(stream.error)) : null,
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

function isHiddenMessage(message: any): boolean {
  // 1. name field check (most reliable)
  if (message?.name === "summary") return true;
  // 2. additional_kwargs check
  const kwargs = message?.additional_kwargs;
  if (kwargs?.train_agent_hidden) return true;
  if (kwargs?.lc_source === "summarization") return true;
  // 3. content fallback
  const content = typeof message?.content === "string" ? message.content : "";
  if (content.startsWith("Here is a summary of the conversation to date:")) return true;
  return false;
}

const SUMMARIZATION_UPDATE_KEYS = new Set([
  "SummarizationMiddleware.before_model",
  "TrainAgentSummarizationMiddleware.before_model",
]);

function getSummarizationMessages(data: unknown): any[] | undefined {
  if (typeof data !== "object" || data === null) return undefined;
  for (const [key, update] of Object.entries(data)) {
    if (!SUMMARIZATION_UPDATE_KEYS.has(key)) continue;
    const messages = (update as any)?.messages;
    if (Array.isArray(messages)) return [...messages];
  }
  return undefined;
}

function messageIdentity(message: any): string | undefined {
  if (message?.tool_call_id) return `tool:${message.tool_call_id}`;
  if (message?.id) return `message:${message.id}`;
  return undefined;
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
