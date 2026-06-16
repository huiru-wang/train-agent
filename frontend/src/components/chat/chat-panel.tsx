"use client";

import { Assistant, type ExternalCommand } from "./assistant";
import { Thread } from "./thread";

interface ChatPanelProps {
  workspaceId: string;
  pptStyle?: string;
  currentPptTaskId?: string;
  onPptTaskIdConsumed?: () => void;
  externalCommand?: ExternalCommand | null;
  onExternalCommandConsumed?: () => void;
}

export function ChatPanel({ workspaceId, pptStyle, currentPptTaskId, onPptTaskIdConsumed, externalCommand, onExternalCommandConsumed }: ChatPanelProps) {
  return (
    <Assistant
      workspaceId={workspaceId}
      pptStyle={pptStyle}
      currentPptTaskId={currentPptTaskId}
      onPptTaskIdConsumed={onPptTaskIdConsumed}
      externalCommand={externalCommand}
      onExternalCommandConsumed={onExternalCommandConsumed}
    >
      <Thread />
    </Assistant>
  );
}
