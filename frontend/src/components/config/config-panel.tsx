"use client";

import { useState } from "react";
import { Palette, Mic, Settings } from "lucide-react";
import { updateWorkspaceConfig } from "@/lib/api";
import {
  StylePickerDialog,
  PPT_STYLES,
} from "./style-picker-dialog";
import {
  VoicePickerDialog,
  VOICES,
} from "./voice-picker-dialog";

interface ConfigPanelProps {
  workspaceId: string;
  pptStyle: string;
  voiceId: string;
  onConfigChange: (key: string, value: string) => void;
}

export function ConfigPanel({
  workspaceId,
  pptStyle,
  voiceId,
  onConfigChange,
}: ConfigPanelProps) {
  const [showStylePicker, setShowStylePicker] = useState(false);
  const [showVoicePicker, setShowVoicePicker] = useState(false);

  const selectedStyle = PPT_STYLES.find((s) => s.id === pptStyle);
  const selectedVoice = VOICES.find((v) => v.id === voiceId);

  const handleStyleSelect = async (styleId: string) => {
    onConfigChange("ppt_style", styleId);
    try {
      await updateWorkspaceConfig(workspaceId, "ppt_style", styleId);
    } catch {
      console.error("Failed to update ppt_style config");
    }
  };

  const handleVoiceSelect = async (voiceId: string) => {
    onConfigChange("voice_id", voiceId);
    try {
      await updateWorkspaceConfig(workspaceId, "voice_id", voiceId);
    } catch {
      console.error("Failed to update voice_id config");
    }
  };

  return (
    <>
      <div className="shrink-0 border-b border-border px-4 py-3">
        <div className="mb-2.5 flex items-center gap-1.5">
          <Settings size={13} className="text-muted-foreground" />
          <h3 className="text-xs font-medium text-muted-foreground">配置</h3>
        </div>

        <div className="flex flex-col gap-2">
          {/* PPT Style */}
          <button
            onClick={() => setShowStylePicker(true)}
            className="flex items-center gap-2.5 rounded-lg border border-border px-3 py-2 text-left transition-colors hover:border-accent/50 hover:bg-muted/50"
          >
            <Palette size={14} className="shrink-0 text-accent/70" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-foreground">
                PPT 风格
              </p>
              <p className="truncate text-[10px] text-muted-foreground">
                {selectedStyle ? `${selectedStyle.cn} ${selectedStyle.name}` : pptStyle}
              </p>
            </div>
          </button>

          {/* Voice */}
          <button
            onClick={() => setShowVoicePicker(true)}
            className="flex items-center gap-2.5 rounded-lg border border-border px-3 py-2 text-left transition-colors hover:border-accent/50 hover:bg-muted/50"
          >
            <Mic size={14} className="shrink-0 text-accent/70" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-foreground">
                语音音色
              </p>
              <p className="truncate text-[10px] text-muted-foreground">
                {selectedVoice?.name ?? voiceId}
              </p>
            </div>
          </button>
        </div>
      </div>

      {showStylePicker && (
        <StylePickerDialog
          selectedId={pptStyle}
          onSelect={handleStyleSelect}
          onClose={() => setShowStylePicker(false)}
        />
      )}

      {showVoicePicker && (
        <VoicePickerDialog
          selectedId={voiceId}
          onSelect={handleVoiceSelect}
          onClose={() => setShowVoicePicker(false)}
        />
      )}
    </>
  );
}
