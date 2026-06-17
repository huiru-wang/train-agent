const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, statusText: string, detail: string) {
    super(detail || `API error: ${status} ${statusText}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const method = options?.method || "GET";
  console.log(`[API] ${method} ${path}`);
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    console.error(`[API] ${method} ${path} failed: ${response.status} ${response.statusText}`);
    let detail = "";
    try {
      const errorData = await response.json();
      detail =
        typeof errorData.detail === "string"
          ? errorData.detail
          : JSON.stringify(errorData.detail ?? errorData);
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(response.status, response.statusText, detail);
  }
  const data = await response.json();
  console.log(`[API] ${method} ${path} →`, Array.isArray(data) ? `${data.length} items` : data);
  return data as T;
}

// --- Workspace ---

export interface Workspace {
  id: string;
  user_id: string;
  name: string;
  thread_id: string | null;
  ext_data: Record<string, unknown>;
  created_at: string;
}

export function createWorkspace(
  userId: string,
  name: string
): Promise<Workspace> {
  return request("/api/workspaces", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, name }),
  });
}

export function listWorkspaces(userId: string): Promise<Workspace[]> {
  return request(`/api/workspaces?user_id=${encodeURIComponent(userId)}`);
}

export function getWorkspace(workspaceId: string): Promise<Workspace> {
  return request(`/api/workspaces/${workspaceId}`);
}

export function deleteWorkspace(workspaceId: string): Promise<void> {
  return request(`/api/workspaces/${workspaceId}`, { method: "DELETE" });
}

export function updateWorkspaceThreadId(workspaceId: string, threadId: string): Promise<{ ok: boolean }> {
  return request(`/api/workspaces/${workspaceId}/thread`, {
    method: "PATCH",
    body: JSON.stringify({ thread_id: threadId }),
  });
}

export function updateWorkspaceConfig(
  workspaceId: string,
  key: string,
  value: unknown
): Promise<{ ok: boolean; ext_data: Record<string, unknown> }> {
  return request(`/api/workspaces/${workspaceId}/config`, {
    method: "PATCH",
    body: JSON.stringify({ key, value }),
  });
}

// --- Messages ---

export interface ThreadMessage {
  id: number;
  thread_id: string;
  workspace_id: string | null;
  message_id: string;
  role: string;
  type: string;
  content: unknown;
  tool_calls: Array<{ id?: string | null; name?: string | null; args?: Record<string, unknown> }>;
  tool_call_id: string | null;
  name: string | null;
  additional_kwargs: Record<string, unknown>;
  response_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ThreadMessagesPage {
  messages: ThreadMessage[];
  next_cursor: number | null;
}

/**
 * List thread messages with turn-based pagination.
 * ``limit`` controls the number of *turns* (a turn = 1 human + following AI/tool messages).
 */
export function listThreadMessages(
  threadId: string,
  options: { limit?: number; before?: number | null } = {}
): Promise<ThreadMessagesPage> {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 10));
  if (options.before) params.set("before", String(options.before));
  return request(`/api/threads/${encodeURIComponent(threadId)}/messages?${params.toString()}`);
}

// --- Documents ---

export interface Document {
  id: string;
  workspace_id: string;
  filename: string;
  file_type: string;
  summary: string | null;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export type DocumentStatus =
  | "uploaded"
  | "processing"
  | "parsing"
  | "parsed"
  | "chunking"
  | "indexing"
  | "summarizing"
  | "ready"
  | "error";

export function listDocuments(workspaceId: string): Promise<Document[]> {
  return request(`/api/workspaces/${workspaceId}/documents`);
}

export async function uploadDocument(
  workspaceId: string,
  file: File
): Promise<Document> {
  console.log(`[API] POST /api/workspaces/${workspaceId}/documents file=${file.name} size=${file.size}`);
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(
    `${API_BASE}/api/workspaces/${workspaceId}/documents`,
    { method: "POST", body: formData }
  );
  if (!response.ok) {
    console.error(`[API] upload failed: ${response.status} ${response.statusText}`);
    throw new Error(`Upload failed: ${response.statusText}`);
  }
  const data = await response.json();
  console.log(`[API] upload result: id=${data.id} status=${data.status}`);
  return data;
}

export function deleteDocument(
  workspaceId: string,
  docId: string
): Promise<void> {
  return request(`/api/workspaces/${workspaceId}/documents/${docId}`, {
    method: "DELETE",
  });
}

// --- Tasks ---

export interface Task {
  id: string;
  workspace_id: string;
  type: string;
  title: string | null;
  status: string;
  result_data: string | null;
  parent_task_id?: string | null;
  children?: Task[];
  created_at: string;
}

export function listTasks(workspaceId: string): Promise<Task[]> {
  return request(`/api/workspaces/${workspaceId}/tasks`);
}

export function deleteTask(workspaceId: string, taskId: string): Promise<{ ok: boolean }> {
  return request(`/api/workspaces/${workspaceId}/tasks/${taskId}`, {
    method: "DELETE",
  });
}

export function saveTaskFile(
  workspaceId: string,
  taskId: string,
  content: string
): Promise<{ ok: boolean }> {
  return request(`/api/workspaces/${workspaceId}/tasks/${taskId}/file`, {
    method: "PUT",
    body: JSON.stringify({ content }),
  });
}

// --- Files ---

export async function fetchFileContent(fileUrl: string): Promise<string> {
  const response = await fetch(fileUrl);
  if (!response.ok) throw new Error(`Failed to fetch file: ${response.status}`);
  return response.text();
}
