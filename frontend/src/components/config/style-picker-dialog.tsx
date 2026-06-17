"use client";

import { useEffect, useRef, useState } from "react";
import { X, Check, ArrowLeft } from "lucide-react";

export interface PptStyle {
  id: string;
  name: string;
  cn: string;
  vibe: string;
  file: string;
  category: "dark" | "light" | "specialty";
}

export const PPT_STYLES: PptStyle[] = [
  // Dark Themes
  { id: "bold-signal", name: "Bold Signal", cn: "浓烈信号", vibe: "暗色渐变底 + 醒目色卡 + 巨大序号，视觉冲击拉满", file: "01-bold-signal.html", category: "dark" },
  { id: "electric-studio", name: "Electric Studio", cn: "电光蓝白", vibe: "上下蓝白分屏，以引用排版为视觉焦点，干净利落", file: "02-electric-studio.html", category: "dark" },
  { id: "creative-voltage", name: "Creative Voltage", cn: "霓虹电压", vibe: "电光蓝与暗色左右分屏，霓虹黄高亮 + 半调纹理", file: "03-creative-voltage.html", category: "dark" },
  { id: "dark-botanical", name: "Dark Botanical", cn: "夜花秘境", vibe: "暗底 + 暖色柔光球 + 优雅衬线斜体，静谧高级", file: "04-dark-botanical.html", category: "dark" },
  // Light Themes
  { id: "notebook-tabs", name: "Notebook Tabs", cn: "活页便签", vibe: "奶白纸卡 + 右侧彩色标签 + 左侧活页孔，编辑质感", file: "05-notebook-tabs.html", category: "light" },
  { id: "pastel-geometry", name: "Pastel Geometry", cn: "马卡龙药丸", vibe: "柔和粉彩底 + 圆角白卡 + 右侧竖排彩色药丸标签", file: "06-pastel-geometry.html", category: "light" },
  { id: "split-pastel", name: "Split Pastel", cn: "蜜桃薰衣草", vibe: "蜜桃/薰衣草左右分屏 + 可爱圆角徽章 + 网格纹理", file: "07-split-pastel.html", category: "light" },
  { id: "vintage-editorial", name: "Vintage Editorial", cn: "复古铅字", vibe: "奶油底色 + 几何线条装饰 + 粗边框按钮，老派印刷感", file: "08-vintage-editorial.html", category: "light" },
  // Specialty Themes
  { id: "neon-cyber", name: "Neon Cyber", cn: "霓虹赛博", vibe: "深空蓝底 + 粒子动画 + 青色/品红霓虹光晕", file: "09-neon-cyber.html", category: "specialty" },
  { id: "terminal-green", name: "Terminal Green", cn: "终端黑客", vibe: "终端窗口 + 闪烁绿光标 + 扫描线，极客美学", file: "10-terminal-green.html", category: "specialty" },
  { id: "swiss-modern", name: "Swiss Modern", cn: "瑞士网格", vibe: "纯白黑红三色 + 可见十二列网格 + 不对称布局", file: "11-swiss-modern.html", category: "specialty" },
  { id: "paper-and-ink", name: "Paper & Ink", cn: "纸墨书香", vibe: "奶油纸质感 + 首字下沉 + 优雅横线分隔，文学气息", file: "12-paper-ink.html", category: "specialty" },
  { id: "global-tech-blue", name: "Global Tech Blue", cn: "地球蓝", vibe: "专业、科技、全球化、商务清新；带有“互联网/AI/数字化”叙事感", file: "13-global-tech-blue.html", category: "specialty" },
];

interface StylePickerDialogProps {
  selectedId: string;
  onSelect: (styleId: string) => void;
  onClose: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  dark: "深色主题",
  light: "浅色主题",
  specialty: "特殊主题",
};

export function StylePickerDialog({
  selectedId,
  onSelect,
  onClose,
}: StylePickerDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const [previewStyle, setPreviewStyle] = useState<PptStyle | null>(null);

  // Close on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (dialogRef.current && !dialogRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (previewStyle) {
          setPreviewStyle(null);
        } else {
          onClose();
        }
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose, previewStyle]);

  const categories = ["dark", "light", "specialty"] as const;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div
        ref={dialogRef}
        className="relative mx-4 flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-border bg-background shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold text-foreground">
            PPT 视觉风格
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
          >
            <X size={16} />
          </button>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-5">
          {categories.map((cat) => {
            const styles = PPT_STYLES.filter((s) => s.category === cat);
            return (
              <div key={cat} className="mb-5 last:mb-0">
                <h3 className="mb-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {CATEGORY_LABELS[cat]}
                </h3>
                <div className="grid grid-cols-2 gap-2.5">
                  {styles.map((style) => {
                    const isSelected = style.id === selectedId;
                    return (
                      <div
                        key={style.id}
                        className={`group relative flex flex-col overflow-hidden rounded-xl border text-left transition-all ${
                          isSelected
                            ? "border-accent ring-1 ring-accent"
                            : "border-border hover:border-accent/50"
                        }`}
                      >
                        {/* PNG thumbnail preview */}
                        <button
                          onClick={() => onSelect(style.id)}
                          className="relative block aspect-[16/10] w-full cursor-pointer overflow-hidden bg-muted"
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={`/ppt-styles/${style.file.replace('.html', '.png')}`}
                            alt={style.cn}
                            className="h-full w-full object-cover"
                          />
                          {/* Selected indicator */}
                          {isSelected && (
                            <div className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-accent">
                              <Check size={12} className="text-background" />
                            </div>
                          )}
                        </button>
                        {/* Info */}
                        <div className="flex items-center justify-between px-3 py-2">
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-xs font-medium text-foreground">
                              {style.cn}
                              <span className="ml-1 font-normal text-muted-foreground">
                                {style.name}
                              </span>
                            </p>
                            <p className="mt-0.5 truncate text-[10px] leading-tight text-muted-foreground">
                              {style.vibe}
                            </p>
                          </div>
                          {/* Full preview button */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setPreviewStyle(style);
                            }}
                            className="ml-2 shrink-0 rounded-md bg-accent/15 px-2.5 py-1 text-[10px] font-medium text-accent transition-colors hover:bg-accent/25"
                          >
                            预览模版
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Full-size preview overlay */}
      {previewStyle && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80"
          onClick={() => setPreviewStyle(null)}
        >
          <div
            className="relative mx-4 flex h-[85vh] w-full max-w-5xl flex-col rounded-2xl border border-border bg-background shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border px-5 py-3">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setPreviewStyle(null)}
                  className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
                >
                  <ArrowLeft size={14} />
                  返回
                </button>
                <div className="h-4 w-px bg-border" />
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-foreground">
                    {previewStyle.cn}
                  </h3>
                  <span className="text-xs text-muted-foreground">
                    {previewStyle.name}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={onClose}
                  className="rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
                  title="关闭"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              <iframe
                src={`/ppt-styles/${previewStyle.file}`}
                title={`${previewStyle.cn} 全屏预览`}
                className="h-full w-full border-0"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
