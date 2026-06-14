"use client";

import { useCallback, useRef, useState, useEffect, type FormEvent, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import remarkGfm from "remark-gfm";
import {
  SendHorizontal,
  Square,
  Bot,
  Brain,
  ChevronDown,
  Copy,
  Check,
  ThumbsUp,
  ThumbsDown,
  FileOutput,
  Loader2,
  Zap,
} from "lucide-react";
import { useStreamContext, useResume } from "./assistant";
import { ClarifyForm } from "./clarify-form";

// ============================================================
// Helpers
// ============================================================

function extractTextContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter(
        (part): part is { type: "text"; text: string } =>
          typeof part === "object" &&
          part !== null &&
          part.type === "text" &&
          typeof part.text === "string",
      )
      .map((part) => part.text)
      .join("");
  }
  return "";
}

interface ExtractedToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

function getToolCallId(value: unknown): string {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }
  if (typeof value === "object" && value !== null) {
    return `{${Object.keys(value as Record<string, unknown>)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify((value as Record<string, unknown>)[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function tryParseJSONObject(rawText: string): Record<string, any> | null {
  const trimmed = rawText.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) {
    return null;
  }

  try {
    const parsed = JSON.parse(trimmed);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function toolCallFingerprint(toolCall: ExtractedToolCall): string {
  return `${toolCall.name}:${stableStringify(toolCall.args)}`;
}

function extractToolCalls(message: any): ExtractedToolCall[] {
  // Prefer dedicated tool_calls property
  if (Array.isArray(message.tool_calls) && message.tool_calls.length > 0) {
    return message.tool_calls
      .filter((toolCall: any) => typeof toolCall?.name === "string")
      .map((toolCall: any) => ({
        id: getToolCallId(toolCall.id),
        name: toolCall.name,
        args: toolCall.args ?? {},
      }));
  }
  // Fallback: extract from content array (useStream puts them here)
  if (Array.isArray(message.content)) {
    return message.content
      .filter(
        (part: any) =>
          typeof part === "object" &&
          part !== null &&
          (part.type === "tool_call" || part.type === "tool_use") &&
          typeof part.name === "string",
      )
      .map((part: any) => ({
        // Historical content tool_call parts may have id: ""; do not invent
        // a real-looking id because tool messages match by tool_call_id.
        id: getToolCallId(part.id),
        name: part.name,
        args: part.args ?? {},
      }));
  }
  return [];
}

/**
 * Check if the last AI message is currently streaming text content,
 * so we can hide the typing indicator when real content is flowing.
 */
function isStreamingContent(messages: any[]): boolean {
  if (messages.length === 0) return false;
  const last = messages[messages.length - 1];
  const type = last._getType?.() || last.type;
  if (type === "ai") {
    const text = extractTextContent(last.content);
    const toolCalls = extractToolCalls(last);
    return text.length > 0 || toolCalls.length > 0;
  }
  // tool message means we're mid-turn, AI will continue
  if (type === "tool") return true;
  return false;
}

// ============================================================
// Thread (root)
// ============================================================

export function Thread() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const { messages, isLoading, pendingMessage, error } = useStreamContext();
  const hasMessages = messages.length > 0 || !!pendingMessage;

  // Auto-scroll on new content
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages.length, isLoading, pendingMessage]);

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-4 py-6 space-y-4">
          {!hasMessages && <EmptyState />}
          <MessageList messages={messages} />
          {pendingMessage && <HumanBubble text={pendingMessage} pending />}
          <InterruptBlock />
          {isLoading && !isStreamingContent(messages) && <TypingIndicator />}
          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              出错了：{error.message}
            </div>
          )}
        </div>
      </div>
      <div className="border-t border-border px-4 py-3">
        <div className="mx-auto max-w-2xl">
          <ChatInput />
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Message list
// ============================================================

/**
 * A "turn" groups all consecutive AI + tool messages between two human messages
 * into a single visual bubble, so tool calls and final text appear together.
 */
interface AITurn {
  id: string;
  aiMessages: any[];
  toolMessages: any[];
}

function groupMessagesIntoTurns(messages: any[]) {
  const turns: Array<{ type: "human"; text: string; id: string } | { type: "ai-turn"; turn: AITurn }> = [];
  let currentTurn: AITurn | null = null;

  for (const msg of messages) {
    const msgType = msg._getType?.() || msg.type;

    if (msgType === "human") {
      if (currentTurn) {
        turns.push({ type: "ai-turn", turn: currentTurn });
        currentTurn = null;
      }
      turns.push({
        type: "human",
        text: typeof msg.content === "string" ? msg.content : "",
        id: msg.id ?? `human-${turns.length}`,
      });
    } else if (msgType === "ai") {
      if (!currentTurn) {
        currentTurn = { id: msg.id ?? `turn-${turns.length}`, aiMessages: [], toolMessages: [] };
      }
      currentTurn.aiMessages.push(msg);
    } else if (msgType === "tool") {
      if (!currentTurn) {
        currentTurn = { id: `turn-${turns.length}`, aiMessages: [], toolMessages: [] };
      }
      currentTurn.toolMessages.push(msg);
    }
  }

  if (currentTurn) {
    turns.push({ type: "ai-turn", turn: currentTurn });
  }

  return turns;
}

function MessageList({ messages }: { messages: any[] }) {
  const turns = groupMessagesIntoTurns(messages);

  return (
    <>
      {turns.map((entry) => {
        if (entry.type === "human") {
          return <HumanBubble key={entry.id} text={entry.text} />;
        }
        return <AITurnBubble key={entry.turn.id} turn={entry.turn} />;
      })}
    </>
  );
}

// ============================================================
// AI turn bubble (merges consecutive AI+tool messages into one bubble)
// ============================================================

// Render item types for ordered interleaved display
type RenderItem =
  | { kind: "reasoning"; key: string; text: string }
  | { kind: "text"; key: string; text: string }
  | { kind: "toolcall"; key: string; tc: ExtractedToolCall; result: any };

function AITurnBubble({ turn }: { turn: AITurn }) {
  const effectiveToolMessages = turn.toolMessages;

  // --- Step 1: Collect all tool calls to build the result map ---
  // We need to know all tool call IDs up front to match results.
  const allToolCallsRaw: ExtractedToolCall[] = [];
  for (const aiMsg of turn.aiMessages) {
    allToolCallsRaw.push(...extractToolCalls(aiMsg));
  }

  // Deduplicate: history can contain the same tool call twice (top-level
  // tool_calls with a real id + content array with id: ""). Keep the real-id
  // version so tool_call_id result matching works correctly.
  const realIdFingerprints = new Set(
    allToolCallsRaw.filter((tc) => tc.id).map((tc) => toolCallFingerprint(tc)),
  );
  const seenIds = new Set<string>();
  const seenFallbackFingerprints = new Set<string>();
  const deduplicatedToolCalls = allToolCallsRaw.filter((tc) => {
    const fingerprint = toolCallFingerprint(tc);
    if (tc.id) {
      if (seenIds.has(tc.id)) return false;
      seenIds.add(tc.id);
      return true;
    }
    if (realIdFingerprints.has(fingerprint)) return false;
    if (seenFallbackFingerprints.has(fingerprint)) return false;
    seenFallbackFingerprints.add(fingerprint);
    return true;
  });

  // --- Step 2: Build tool result map ---
  const toolResultMap = new Map<string, any>();
  const hasRealIds = deduplicatedToolCalls.some((tc) => tc.id && tc.id.length > 0);

  if (hasRealIds) {
    for (const toolMsg of effectiveToolMessages) {
      const callId = toolMsg.tool_call_id;
      if (callId) toolResultMap.set(callId, toolMsg);
    }
  } else {
    // Positional matching when IDs are missing
    deduplicatedToolCalls.forEach((tc, i) => {
      if (!tc.id) tc.id = `pos-${i}`;
      if (i < effectiveToolMessages.length) {
        toolResultMap.set(tc.id, effectiveToolMessages[i]);
      }
    });
  }

  // Build a lookup by fingerprint for deduplication during ordered traversal
  const dedupedByFingerprint = new Map<string, ExtractedToolCall>();
  for (const tc of deduplicatedToolCalls) {
    dedupedByFingerprint.set(toolCallFingerprint(tc), tc);
  }

  // --- Step 3: Build ordered render items by traversing each AI message's
  // content array in sequence, preserving the model's actual output order.
  // This correctly handles patterns like: tool → text → tool, text + tool, etc.
  const renderItems: RenderItem[] = [];
  const seenRenderIds = new Set<string>();
  let textIndex = 0;
  let allText = "";

  for (const aiMsg of turn.aiMessages) {
    // Reasoning (thinking blocks) always come first within a message
    const reasoning = aiMsg.additional_kwargs?.reasoning_content as string | undefined;
    if (reasoning) {
      renderItems.push({ kind: "reasoning", key: `reasoning-${renderItems.length}`, text: reasoning });
    }

    if (Array.isArray(aiMsg.content)) {
      // Traverse content parts in order to preserve interleaving
      for (const part of aiMsg.content as Array<Record<string, unknown>>) {
        if (part.type === "text" && typeof part.text === "string" && (part.text as string).trim()) {
          const text = part.text as string;
          const key = `text-${textIndex++}`;
          renderItems.push({ kind: "text", key, text });
          allText += (allText ? "\n\n" : "") + text;
        } else if (part.type === "tool_call" || part.type === "tool_use") {
          // Find the deduplicated version of this tool call (which has the correct id)
          const partFingerprint = toolCallFingerprint({
            id: getToolCallId(part.id as string),
            name: (part.name as string) || "",
            args: (part.args as Record<string, unknown>) ?? {},
          });
          const canonicalTc = dedupedByFingerprint.get(partFingerprint);
          if (!canonicalTc) continue;

          // Skip if already rendered (handles duplication between content and tool_calls)
          const renderId = canonicalTc.id || partFingerprint;
          if (seenRenderIds.has(renderId)) continue;
          seenRenderIds.add(renderId);

          renderItems.push({
            kind: "toolcall",
            key: `tc-${renderId}`,
            tc: canonicalTc,
            result: toolResultMap.get(canonicalTc.id || ""),
          });
        }
      }
    } else {
      // Fallback: plain string content
      const text = extractTextContent(aiMsg.content);
      if (text.trim()) {
        const key = `text-${textIndex++}`;
        renderItems.push({ kind: "text", key, text });
        allText += (allText ? "\n\n" : "") + text;
      }
      // Also emit any top-level tool_calls not already rendered via content array
      for (const tc of extractToolCalls(aiMsg)) {
        const renderId = tc.id || toolCallFingerprint(tc);
        if (seenRenderIds.has(renderId)) continue;
        seenRenderIds.add(renderId);
        const canonical = dedupedByFingerprint.get(toolCallFingerprint(tc)) ?? tc;
        renderItems.push({
          kind: "toolcall",
          key: `tc-${renderId}`,
          tc: canonical,
          result: toolResultMap.get(canonical.id || ""),
        });
      }
    }
  }

  // Emit any tool calls from top-level tool_calls that weren't captured by
  // the content-array traversal (e.g. streamed messages that only have tool_calls)
  for (const tc of deduplicatedToolCalls) {
    const renderId = tc.id || toolCallFingerprint(tc);
    if (seenRenderIds.has(renderId)) continue;
    seenRenderIds.add(renderId);
    renderItems.push({
      kind: "toolcall",
      key: `tc-${renderId}`,
      tc,
      result: toolResultMap.get(tc.id || ""),
    });
  }

  if (renderItems.length === 0) return null;

  return (
    <div className="group">
      <div className="min-w-0 space-y-2">
        {renderItems.map((item) => {
          if (item.kind === "reasoning") {
            return <ReasoningBlock key={item.key} text={item.text} />;
          }
          if (item.kind === "text") {
            return (
              <div key={item.key} className="prose prose-invert prose-sm max-w-none">
                <MarkdownWithCitations text={item.text} />
              </div>
            );
          }
          if (item.kind === "toolcall") {
            return (
              <ToolCallCard
                key={item.key}
                toolCall={item.tc}
                result={item.result}
              />
            );
          }
          return null;
        })}

        {allText && <MessageActions content={allText} />}
      </div>
    </div>
  );
}

// ============================================================
// Tool call cards
// ============================================================

// Tool name -> Chinese label mapping
const TOOL_LABELS: Record<string, string> = {
  terminal: "命令执行",
  rag_search: "知识库检索",
  load_skill: "读取技能",
  save_output: "保存产出",
  clarify_form: "信息收集",
};

function getToolLabel(name: string): string {
  return TOOL_LABELS[name] || name;
}

interface ToolDisplayContext {
  toolCall: ExtractedToolCall;
  result: any;
  isDone: boolean;
}

interface ToolDisplayConfig {
  label: (ctx: ToolDisplayContext) => string;
  expandable: boolean | ((ctx: ToolDisplayContext) => boolean);
  summary?: (ctx: ToolDisplayContext) => ReactNode;
  details?: (ctx: ToolDisplayContext) => ReactNode;
}

function truncateText(text: string, max = 90): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 1)}…`;
}

function getToolArgString(args: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = args[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
  }
  return "";
}

function extractToolResultText(result: unknown): string {
  if (!result) return "";
  if (typeof result === "string") return result;
  if (typeof result === "object" && result !== null) {
    const content = (result as { content?: unknown }).content;
    if (typeof content === "string") return content;
    if (Array.isArray(content)) {
      return content
        .map((part) => {
          if (typeof part === "string") return part;
          if (
            typeof part === "object" &&
            part !== null &&
            "text" in part &&
            typeof (part as { text?: unknown }).text === "string"
          ) {
            return (part as { text: string }).text;
          }
          return "";
        })
        .filter(Boolean)
        .join("\n");
    }
  }
  return "";
}

function ToolTextBlock({ value }: { value: string }) {
  return (
    <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-border/50 bg-background/70 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
      {value || "无返回内容"}
    </pre>
  );
}

const DEFAULT_TOOL_DISPLAY: ToolDisplayConfig = {
  label: ({ toolCall }) => getToolLabel(toolCall.name),
  expandable: false,
};

const TOOL_DISPLAY_CONFIG: Record<string, ToolDisplayConfig> = {
  rag_search: {
    label: () => "知识库检索",
    expandable: true,
    summary: ({ toolCall }) => {
      const query = getToolArgString(toolCall.args, ["query"]);
      return query ? `查询：${truncateText(query)}` : "查询知识库";
    },
    details: ({ result }) => <ToolTextBlock value={extractToolResultText(result)} />,
  },
  terminal: {
    label: () => "命令执行",
    expandable: false,
    summary: () => "",
  },
  load_skill: {
    label: ({ toolCall }) => {
      const skillName = getToolArgString(toolCall.args, ["skill_name", "name"]);
      const filePaths = toolCall.args["file_paths"] as string[] | undefined;
      if (filePaths && filePaths.length > 0) {
        return skillName ? `读取技能：${skillName}` : "读取技能";
      }
      return skillName ? `读取技能：${skillName}` : "读取技能";
    },
    expandable: true,
    summary: ({ toolCall }) => {
      const skillName = getToolArgString(toolCall.args, ["skill_name", "name"]);
      const filePaths = toolCall.args["file_paths"] as string[] | undefined;
      if (filePaths && filePaths.length > 0) {
        return filePaths.join(", ");
      }
      return "SKILL.md";
    },
    details: ({ result }) => {
      const rawText = extractToolResultText(result);
      // Reusable markdown components
      const mdComponents = {
        code: ({ className, children, ...rest }: any) => {
          const match = /language-(\w+)/.exec(className || "");
          const codeString = String(children).replace(/\n$/, "");
          if (match) {
            return (
              <SyntaxHighlighter
                style={oneDark}
                language={match[1]}
                PreTag="div"
                customStyle={{ margin: 0, borderRadius: "0.5rem", fontSize: "0.85em" }}
              >
                {codeString}
              </SyntaxHighlighter>
            );
          }
          return <code className={className} {...rest}>{children}</code>;
        },
        table: ({ children, ...rest }: any) => (
          <div className="overflow-x-auto">
            <table className="w-max min-w-full" {...rest}>{children}</table>
          </div>
        ),
        h1: ({ children, ...rest }: any) => <h1 className="text-lg font-bold mt-4 mb-2" {...rest}>{children}</h1>,
        h2: ({ children, ...rest }: any) => <h2 className="text-base font-semibold mt-3 mb-2" {...rest}>{children}</h2>,
        h3: ({ children, ...rest }: any) => <h3 className="text-sm font-medium mt-2 mb-1" {...rest}>{children}</h3>,
        p: ({ children, ...rest }: any) => <p className="my-1" {...rest}>{children}</p>,
        ul: ({ children, ...rest }: any) => <ul className="list-disc list-inside my-1 space-y-1" {...rest}>{children}</ul>,
        ol: ({ children, ...rest }: any) => <ol className="list-decimal list-inside my-1 space-y-1" {...rest}>{children}</ol>,
        li: ({ children, ...rest }: any) => <li className="text-xs" {...rest}>{children}</li>,
        blockquote: ({ children, ...rest }: any) => <blockquote className="border-l-2 border-accent/50 pl-2 my-1 text-xs" {...rest}>{children}</blockquote>,
        a: ({ href, children, ...rest }: any) => <a href={href} className="text-accent underline" target="_blank" rel="noopener noreferrer" {...rest}>{children}</a>,
      };

      const data = tryParseJSONObject(rawText);
      if (data?.files) {
        const entries = Object.entries(data.files);
        if (entries.length === 0) {
          return <ToolTextBlock value="(no content)" />;
        }
        return (
          <div className="max-h-96 overflow-y-auto space-y-3">
            {entries.map(([path, content]) => (
              <div key={path}>
                <p className="text-[10px] text-accent mb-1 font-medium">{path}</p>
                <div className="rounded border border-border/40 bg-background/50 p-2 max-h-64 overflow-y-auto">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                    {String(content ?? "")}
                  </ReactMarkdown>
                </div>
              </div>
            ))}
          </div>
        );
      }
      if (typeof data?.content === "string") {
        // Strip YAML frontmatter if present
        let content = data.content;
        if (content.startsWith("---")) {
          const endIdx = content.indexOf("---", 3);
          if (endIdx !== -1) {
            content = content.slice(endIdx + 3).trim();
          }
        }
        return (
          <div className="max-h-96 overflow-y-auto rounded border border-border/40 bg-background/50 p-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {content}
            </ReactMarkdown>
          </div>
        );
      }
      return <ToolTextBlock value={rawText} />;
    },
  },
  save_output: {
    label: () => "保存产出",
    expandable: false,
    summary: ({ toolCall }) => {
      const filename = getToolArgString(toolCall.args, ["filename"]);
      if (filename) return filename;

      const title = getToolArgString(toolCall.args, ["title"]);
      const type = getToolArgString(toolCall.args, ["type"]);
      if (title) {
        const extensionMap: Record<string, string> = { ppt: ".html", report: ".md" };
        const safeTitle = title.replace(/ /g, "_").replace(/\//g, "_");
        return `${safeTitle}${extensionMap[type] ?? ".txt"}`;
      }
      return "";
    },
  },
  clarify_form: {
    label: () => "信息收集",
    expandable: true,
  },
};

function ClarifyFormSummary({
  toolCall,
  result,
}: {
  toolCall: ExtractedToolCall;
  result: any;
}) {
  const [expanded, setExpanded] = useState(false);

  const title = (toolCall.args as Record<string, unknown>)?.title as string || "信息收集";
  const fields = (toolCall.args as Record<string, unknown>)?.fields as Array<{
    name: string;
    label: string;
  }> | undefined;

  const resultText = extractToolResultText(result);
  let userValues: Record<string, unknown> = {};
  try {
    userValues = JSON.parse(resultText);
  } catch {
    // Fallback: try parsing legacy Python dict format
    const dictMatch = resultText.match(/用户填写的表单结果:\s*(\{[\s\S]*\})/);
    if (dictMatch) {
      try {
        const jsonStr = dictMatch[1]
          .replace(/'/g, '"')
          .replace(/True/g, "true")
          .replace(/False/g, "false")
          .replace(/None/g, "null");
        userValues = JSON.parse(jsonStr);
      } catch { /* use empty */ }
    }
  }

  // User cancelled the form — show a compact cancelled badge
  if (userValues.cancelled) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border/50 bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground not-prose">
        <span className="text-yellow-400">✗</span>
        <span className="shrink-0 font-medium">信息收集</span>
        <span className="min-w-0 flex-1 truncate text-muted-foreground/80">{title} — 已取消</span>
      </div>
    );
  }

  const entries = fields
    ? fields
        .map((field) => ({
          label: field.label,
          value: userValues[field.name],
        }))
        .filter((entry) => entry.value !== undefined && entry.value !== "")
    : Object.entries(userValues).map(([key, value]) => ({
        label: key,
        value,
      }));

  return (
    <div className="overflow-hidden rounded-lg border border-border/50 bg-muted/30 text-xs text-muted-foreground not-prose">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left cursor-pointer hover:bg-muted/40"
      >
        <span className="text-green-400">✓</span>
        <span className="shrink-0 font-medium">信息收集</span>
        <span className="min-w-0 flex-1 truncate text-muted-foreground/80">
          {title}
        </span>
        <ChevronDown
          size={13}
          className={`ml-auto shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>
      {expanded && (
        <div className="border-t border-border/40 px-3 py-2 space-y-1.5">
          {entries.map(({ label, value }) => (
            <div key={label} className="flex items-start gap-2">
              <span className="shrink-0 text-muted-foreground/70 min-w-[5rem]">
                {label}:
              </span>
              <span className="text-foreground/90">
                {Array.isArray(value) ? value.join("、") : String(value)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ToolCallCard({
  toolCall,
  result,
}: {
  toolCall: ExtractedToolCall;
  result: any;
}) {
  const name = toolCall.name;
  const isDone = !!result;
  const [expanded, setExpanded] = useState(false);

  // clarify_form: 未完成时由 InterruptBlock 渲染交互式表单；已完成时显示只读摘要
  if (name === "clarify_form") {
    if (!isDone) return null;
    return <ClarifyFormSummary toolCall={toolCall} result={result} />;
  }

  const context: ToolDisplayContext = { toolCall, result, isDone };
  const config = TOOL_DISPLAY_CONFIG[name] ?? DEFAULT_TOOL_DISPLAY;
  const expandable =
    typeof config.expandable === "function"
      ? config.expandable(context)
      : config.expandable;
  const label = config.label(context);
  const summary = config.summary?.(context);
  const details = config.details?.(context);
  const canExpand = isDone && expandable && !!details;

  if (!isDone) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border/50 bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground not-prose">
        <Loader2 size={13} className="animate-spin" />
        <span className="font-medium">{label}...</span>
        {summary && <span className="min-w-0 truncate text-muted-foreground/80">{summary}</span>}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border/50 bg-muted/30 text-xs text-muted-foreground not-prose">
      <button
        type="button"
        onClick={() => {
          if (canExpand) setExpanded((value) => !value);
        }}
        disabled={!canExpand}
        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left ${canExpand ? "cursor-pointer hover:bg-muted/40" : "cursor-default"
          }`}
      >
        <span className="text-green-400">✓</span>
        <span className="shrink-0 font-medium">{label}</span>
        {summary && (
          <span className="min-w-0 flex-1 truncate text-muted-foreground/80">
            {summary}
          </span>
        )}
        {canExpand && (
          <ChevronDown
            size={13}
            className={`ml-auto shrink-0 transition-transform ${expanded ? "rotate-180" : ""
              }`}
          />
        )}
      </button>
      {canExpand && expanded && (
        <div className="border-t border-border/40 px-3 py-2">{details}</div>
      )}
    </div>
  );
}

// ============================================================
// Interrupt block
// ============================================================

function normalizeFieldOptions(options: unknown): string[] | undefined {
  if (Array.isArray(options)) {
    const normalized = options
      .map((option) => {
        if (typeof option === "string") return option;
        if (typeof option === "number" || typeof option === "boolean") {
          return String(option);
        }
        if (typeof option === "object" && option !== null) {
          const record = option as Record<string, unknown>;
          const value = record.label ?? record.value ?? record.name ?? record.text;
          if (typeof value === "string") return value;
          if (typeof value === "number" || typeof value === "boolean") {
            return String(value);
          }
        }
        return "";
      })
      .map((option) => option.trim())
      .filter(Boolean);
    return normalized.length > 0 ? normalized : undefined;
  }

  if (typeof options === "string") {
    const normalized = options
      .split(/[\n,，、]/)
      .map((option) => option.trim())
      .filter(Boolean);
    return normalized.length > 0 ? normalized : undefined;
  }

  return undefined;
}

function InterruptBlock() {
  const { interrupt } = useStreamContext();
  const onResume = useResume();
  // 本地已提交标记：resume 发出后立即隐藏表单，不等 stream 消息更新。
  // 防止重启后重复点击提交触发 "no pending protocol interrupt" 错误。
  const [localSubmitted, setLocalSubmitted] = useState(false);

  if (!interrupt || interrupt.value === undefined) return null;
  if (localSubmitted) return null;

  const interruptValue = interrupt.value as Record<string, unknown>;

  const handleSubmit = async (values: Record<string, string | string[]>) => {
    setLocalSubmitted(true);
    try {
      await onResume(values);
    } catch (err) {
      console.error("[InterruptBlock] resume failed:", err);
      setLocalSubmitted(false);
    }
  };

  if (interruptValue.fields && Array.isArray(interruptValue.fields)) {
    const fields = (
      interruptValue.fields as Array<Record<string, unknown>>
    ).map((field) => ({
      name: (field.name as string) || "",
      label: (field.label as string) || "",
      type: (field.type as "text" | "select" | "multiselect") || "text",
      options: normalizeFieldOptions(field.options),
      required: field.required !== false,
    }));

    return (
      <div>
        <div className="min-w-0">
          <ClarifyForm
            title={(interruptValue.title as string) || "请填写信息"}
            description={(interruptValue.description as string) || ""}
            fields={fields}
            onSubmit={handleSubmit}
          />
        </div>
      </div>
    );
  }

  return null;
}

// ============================================================
// Bubbles & indicators
// ============================================================

function HumanBubble({
  text,
  pending,
}: {
  text: string;
  pending?: boolean;
}) {
  // Parse "/command rest" pattern to render pill + text
  // Allow command to be sent alone (e.g. "/ppt") or with additional text
  const slashMatch = text.match(/^(\/\w+)(?:\s([\s\S]*))?$/);
  const command = slashMatch
    ? SLASH_COMMANDS.find((c) => c.command === slashMatch[1])
    : null;
  const displayText = command ? (slashMatch![2] || "") : text;

  return (
    <div className="flex justify-end">
      <div
        className={`max-w-[80%] rounded-2xl rounded-br-md bg-accent/20 px-4 py-2.5 text-sm text-foreground ${pending ? "opacity-70" : ""
          }`}
      >
        {command && (
          <span className="inline-flex items-center gap-1 rounded-full bg-accent/15 border border-accent/30 px-2 py-0.5 text-xs text-accent mr-2 align-middle">
            {command.icon}
            <span className="font-medium">{command.label}</span>
          </span>
        )}
        <span className="whitespace-pre-wrap">{displayText}</span>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-3 py-20 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/15 text-accent">
        <Bot size={24} />
      </div>
      <h3 className="text-base font-medium text-foreground">培训助手</h3>
      <p className="max-w-sm text-sm text-muted-foreground">
        上传培训文档后，我可以帮你理解内容、回答问题，还能用
        <code className="mx-1 rounded bg-muted px-1.5 py-0.5 text-xs text-accent">
          /ppt
        </code>
        生成培训PPT
      </p>
    </div>
  );
}

// ============================================================
// Slash commands
// ============================================================

interface SlashCommand {
  command: string;
  label: string;
  description: string;
  icon: React.ReactNode;
}

const SLASH_COMMANDS: SlashCommand[] = [
  {
    command: "/ppt",
    label: "生成培训PPT",
    description: "基于知识库文档生成 HTML 演示文稿",
    icon: <FileOutput size={14} />,
  },
];

function SlashCommandMenu({
  filter,
  selectedIndex,
  onSelect,
}: {
  filter: string;
  selectedIndex: number;
  onSelect: (cmd: SlashCommand) => void;
}) {
  const filtered = SLASH_COMMANDS.filter(
    (cmd) =>
      cmd.command.includes(filter.toLowerCase()) ||
      cmd.label.includes(filter),
  );

  if (filtered.length === 0) return null;

  return (
    <div className="absolute bottom-full left-0 right-0 mb-2 rounded-xl border border-border bg-[#1e1e2e] shadow-xl overflow-hidden z-50">
      <div className="px-3 py-1.5 text-[11px] text-muted-foreground/60 uppercase tracking-wider border-b border-border/50">
        可用命令
      </div>
      {filtered.map((cmd, index) => (
        <button
          key={cmd.command}
          type="button"
          onMouseDown={(e) => {
            e.preventDefault();
            onSelect(cmd);
          }}
          className={`flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors ${index === selectedIndex
            ? "bg-accent/15 text-foreground"
            : "text-muted-foreground hover:bg-muted/30 hover:text-foreground"
            }`}
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
            {cmd.icon}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-accent">
                {cmd.command}
              </span>
              <span className="text-sm">{cmd.label}</span>
            </div>
            <p className="text-xs text-muted-foreground/70 truncate">
              {cmd.description}
            </p>
          </div>
        </button>
      ))}
    </div>
  );
}

// ============================================================
// Chat input
// ============================================================

function ChatInput() {
  const [text, setText] = useState("");
  const [activeCommand, setActiveCommand] = useState<SlashCommand | null>(null);
  const [showCommands, setShowCommands] = useState(false);
  const [selectedCmdIndex, setSelectedCmdIndex] = useState(0);
  const { submit, stop, isLoading } = useStreamContext();
  const inputRef = useRef<HTMLInputElement>(null);

  const slashFilter = text.startsWith("/") ? text : "";
  const filteredCommands = SLASH_COMMANDS.filter(
    (cmd) =>
      cmd.command.includes(slashFilter.toLowerCase()) ||
      cmd.label.includes(slashFilter),
  );
  const isMenuVisible = showCommands && !activeCommand && filteredCommands.length > 0;

  const selectCommand = useCallback((cmd: SlashCommand) => {
    setActiveCommand(cmd);
    setText("");
    setShowCommands(false);
    setSelectedCmdIndex(0);
    inputRef.current?.focus();
  }, []);

  const clearCommand = useCallback(() => {
    setActiveCommand(null);
  }, []);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setText(value);
    if (!activeCommand && value.startsWith("/")) {
      setShowCommands(true);
      setSelectedCmdIndex(0);
    } else {
      setShowCommands(false);
    }
  }, [activeCommand]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Backspace on empty input clears the active pill
      if (e.key === "Backspace" && text === "" && activeCommand) {
        e.preventDefault();
        clearCommand();
        return;
      }
      if (!isMenuVisible) return;
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedCmdIndex((prev) =>
          prev <= 0 ? filteredCommands.length - 1 : prev - 1,
        );
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedCmdIndex((prev) =>
          prev >= filteredCommands.length - 1 ? 0 : prev + 1,
        );
      } else if (e.key === "Tab" || e.key === "Enter") {
        e.preventDefault();
        const cmd = filteredCommands[selectedCmdIndex];
        if (cmd) selectCommand(cmd);
      } else if (e.key === "Escape") {
        setShowCommands(false);
      }
    },
    [isMenuVisible, filteredCommands, selectedCmdIndex, selectCommand, text, activeCommand, clearCommand],
  );

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (isMenuVisible) return;
    if (isLoading) return;
    // Allow slash command to be sent alone, or with additional text
    const content = activeCommand
      ? (text.trim() ? `${activeCommand.command} ${text.trim()}` : activeCommand.command)
      : text.trim();
    if (!content) return;
    submit(content);
    setText("");
    setActiveCommand(null);
    setShowCommands(false);
  };

  const skipNextBlurRef = useRef(false);

  const openSkillMenu = useCallback(() => {
    if (activeCommand) {
      clearCommand();
      return;
    }
    skipNextBlurRef.current = true;
    setText("/");
    setShowCommands(true);
    setSelectedCmdIndex(0);
    inputRef.current?.focus();
  }, [activeCommand, clearCommand]);

  return (
    <div className="relative">
      {isMenuVisible && (
        <SlashCommandMenu
          filter={slashFilter}
          selectedIndex={selectedCmdIndex}
          onSelect={selectCommand}
        />
      )}
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 rounded-xl border border-border bg-muted/50 px-3 py-2 focus-within:border-accent/40"
      >
        <button
          type="button"
          onMouseDown={(e) => { e.preventDefault(); openSkillMenu(); }}
          title="技能"
          className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors ${activeCommand
            ? "bg-accent/20 text-accent"
            : "text-muted-foreground hover:bg-muted/50 hover:text-accent"
            }`}
        >
          <Zap size={16} />
        </button>

        {/* Pill token for active command */}
        {activeCommand && (
          <span className="flex items-center gap-1.5 rounded-full bg-accent/15 border border-accent/30 px-2.5 py-1 text-xs text-accent shrink-0 animate-in fade-in slide-in-from-left-2 duration-150">
            {activeCommand.icon}
            <span className="font-medium">{activeCommand.label}</span>
          </span>
        )}

        <input
          ref={inputRef}
          type="text"
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onBlur={() => {
            if (skipNextBlurRef.current) {
              skipNextBlurRef.current = false;
              return;
            }
            setTimeout(() => setShowCommands(false), 150);
          }}
          placeholder={activeCommand ? "输入具体要求..." : "输入消息... 输入 / 查看可用命令"}
          disabled={isLoading}
          className="min-h-[36px] flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
          autoFocus
        />
        {isLoading ? (
          <button
            type="button"
            onClick={() => stop()}
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-destructive/20 text-destructive transition-colors hover:bg-destructive/30"
          >
            <Square size={14} />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!text.trim() && !activeCommand}
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-accent-foreground transition-colors hover:bg-accent/90 disabled:opacity-30"
          >
            <SendHorizontal size={14} />
          </button>
        )}
      </form>
    </div>
  );
}

// ============================================================
// Markdown with citations
// ============================================================

const REF_PATTERN = /\{\{ref:([^|]+)\|([^}]+)\}\}/g;
const CITE_HREF_PREFIX = "#__cite__";

interface CitationEntry {
  docName: string;
  detail: string;
}

function MarkdownWithCitations({ text }: { text: string }) {
  const citations: CitationEntry[] = [];
  const sanitized = text.replace(
    REF_PATTERN,
    (_m, docName: string, detail: string) => {
      citations.push({ docName, detail });
      return `[⟦${citations.length}⟧](${CITE_HREF_PREFIX}${citations.length})`;
    },
  );

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children, ...rest }) => {
          if (href?.startsWith(CITE_HREF_PREFIX)) {
            const idx = parseInt(href.slice(CITE_HREF_PREFIX.length), 10);
            const entry = citations[idx - 1];
            if (entry)
              return (
                <CitationBadge
                  index={idx}
                  docName={entry.docName}
                  detail={entry.detail}
                />
              );
          }
          return (
            <a href={href} {...rest}>
              {children}
            </a>
          );
        },
        table: ({ children, ...rest }) => (
          <div className="overflow-x-auto">
            <table className="w-max min-w-full" {...rest}>
              {children}
            </table>
          </div>
        ),
        code: ({ className, children, ...rest }) => {
          const match = /language-(\w+)/.exec(className || "");
          const codeString = String(children).replace(/\n$/, "");
          if (match) {
            return (
              <SyntaxHighlighter
                style={oneDark}
                language={match[1]}
                PreTag="div"
                customStyle={{
                  margin: 0,
                  borderRadius: "0.5rem",
                  fontSize: "0.85em",
                }}
              >
                {codeString}
              </SyntaxHighlighter>
            );
          }
          return (
            <code className={className} {...rest}>
              {children}
            </code>
          );
        },
      }}
    >
      {sanitized}
    </ReactMarkdown>
  );
}

function CitationBadge({
  index,
  docName,
  detail,
}: {
  index: number;
  docName: string;
  detail: string;
}) {
  const [show, setShow] = useState(false);
  const badgeRef = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  const onEnter = useCallback(() => {
    if (badgeRef.current) {
      const r = badgeRef.current.getBoundingClientRect();
      setPos({ top: r.top - 8, left: r.left + r.width / 2 });
    }
    setShow(true);
  }, []);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={onEnter}
      onMouseLeave={() => setShow(false)}
    >
      <span
        ref={badgeRef}
        className="ml-0.5 inline-flex h-[18px] min-w-[18px] cursor-default items-center justify-center rounded-full bg-emerald-500/20 px-1 text-[10px] font-semibold text-emerald-400 align-super leading-none"
      >
        {index}
      </span>
      {show && (
        <span
          className="fixed z-[9999] w-max max-w-xs -translate-x-1/2 -translate-y-full rounded-lg border border-border bg-[#1e1e2e] px-3 py-2 text-xs text-foreground shadow-xl"
          style={{ top: pos.top, left: pos.left }}
        >
          <span className="font-medium text-emerald-400">📄 {docName}</span>
          <br />
          <span className="text-muted-foreground">{detail}</span>
        </span>
      )}
    </span>
  );
}

// ============================================================
// Reasoning block
// ============================================================

function ReasoningBlock({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  if (!text?.trim()) return null;
  const preview =
    text.length > 120 ? text.slice(0, 120) + "..." : text;

  return (
    <div className="rounded-lg border border-accent/20 bg-accent/5 not-prose">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-accent/80 hover:text-accent"
      >
        <Brain size={13} />
        <span>思考过程 ({text.length} 字符)</span>
        <ChevronDown
          size={13}
          className={`ml-auto transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>
      {expanded ? (
        <pre className="border-t border-accent/10 px-3 py-2 text-xs text-muted-foreground whitespace-pre-wrap max-h-60 overflow-y-auto">
          {text}
        </pre>
      ) : (
        <p className="px-3 pb-2 text-[11px] text-muted-foreground/70 italic">
          {preview}
        </p>
      )}
    </div>
  );
}

// ============================================================
// Message actions
// ============================================================

function MessageActions({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<"like" | "dislike" | null>(null);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard may fail */
    }
  }, [content]);

  return (
    <div className="mt-1.5 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
      <button
        onClick={handleCopy}
        className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
        title="复制消息"
      >
        {copied ? (
          <Check size={14} className="text-green-400" />
        ) : (
          <Copy size={14} />
        )}
      </button>
      <button
        onClick={() =>
          setFeedback(feedback === "like" ? null : "like")
        }
        className={`rounded-md p-1 transition-colors ${feedback === "like"
          ? "text-green-400"
          : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
          }`}
        title="有帮助"
      >
        <ThumbsUp size={14} />
      </button>
      <button
        onClick={() =>
          setFeedback(feedback === "dislike" ? null : "dislike")
        }
        className={`rounded-md p-1 transition-colors ${feedback === "dislike"
          ? "text-red-400"
          : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
          }`}
        title="没有帮助"
      >
        <ThumbsDown size={14} />
      </button>
    </div>
  );
}
