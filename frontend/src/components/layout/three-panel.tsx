"use client";

import { useState, useCallback, useRef } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";

interface ThreePanelProps {
  left: React.ReactNode;
  center: React.ReactNode;
  right: React.ReactNode;
}

const MIN_SIDE_WIDTH = 240;
const MAX_SIDE_WIDTH = 400;
const DEFAULT_LEFT_WIDTH = 280;
const DEFAULT_RIGHT_WIDTH = 300;

export function ThreePanel({ left, center, right }: ThreePanelProps) {
  const [leftWidth, setLeftWidth] = useState(DEFAULT_LEFT_WIDTH);
  const [rightWidth, setRightWidth] = useState(DEFAULT_RIGHT_WIDTH);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback(
    (side: "left" | "right") => (event: React.MouseEvent) => {
      event.preventDefault();
      const startX = event.clientX;
      const startLeftWidth = leftWidth;
      const startRightWidth = rightWidth;

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const deltaX = moveEvent.clientX - startX;
        if (side === "left") {
          const newWidth = Math.min(
            MAX_SIDE_WIDTH,
            Math.max(MIN_SIDE_WIDTH, startLeftWidth + deltaX)
          );
          setLeftWidth(newWidth);
        } else {
          const newWidth = Math.min(
            MAX_SIDE_WIDTH,
            Math.max(MIN_SIDE_WIDTH, startRightWidth - deltaX)
          );
          setRightWidth(newWidth);
        }
      };

      const handleMouseUp = () => {
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [leftWidth, rightWidth]
  );

  return (
    <div ref={containerRef} className="flex h-full w-full overflow-hidden">
      {/* Left Panel */}
      <div
        className="flex-shrink-0 overflow-y-auto border-r border-border"
        style={{ width: leftWidth }}
      >
        {left}
      </div>

      {/* Left Resize Handle */}
      <div
        className="w-1 flex-shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-accent/30"
        onMouseDown={handleMouseDown("left")}
      />

      {/* Center Panel */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {center}
      </div>

      {/* Right Sidebar Toggle */}
      <div className="flex w-8 flex-shrink-0 flex-col items-center border-l border-border bg-background">
        <button
          type="button"
          onClick={() => setRightCollapsed((value) => !value)}
          className="mt-2 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-expanded={!rightCollapsed}
          aria-label={rightCollapsed ? "展开产出侧边栏" : "收起产出侧边栏"}
          title={rightCollapsed ? "展开产出" : "收起产出"}
        >
          {rightCollapsed ? (
            <PanelRightOpen size={16} />
          ) : (
            <PanelRightClose size={16} />
          )}
        </button>
        {!rightCollapsed && (
          <div
            className="mt-2 w-full flex-1 cursor-col-resize bg-transparent transition-colors hover:bg-accent/20"
            onMouseDown={handleMouseDown("right")}
            title="拖拽调整产出侧边栏宽度"
          />
        )}
      </div>

      {/* Right Panel */}
      {!rightCollapsed && (
        <div
          className="flex-shrink-0 overflow-y-auto border-l border-border"
          style={{ width: rightWidth }}
        >
          {right}
        </div>
      )}
    </div>
  );
}
