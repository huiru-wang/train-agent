"use client";

import { Assistant } from "./assistant";
import { Thread } from "./thread";

interface ChatPanelProps {
  workspaceId: string;
}

export function ChatPanel({ workspaceId }: ChatPanelProps) {
  return (
    <Assistant workspaceId={workspaceId}>
      <Thread />
    </Assistant>
  );
}
