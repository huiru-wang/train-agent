import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Directory containing prompt template files
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# ============================================================
# Train-agent Prompt
# ============================================================

SYSTEM_PROMPT = """你是一名资深企业培训专家，专注于基于知识库文档为用户提供专业、结构化的培训咨询服务。

## 核心职责
- 基于用户上传的培训文档进行深度问答
- 帮助用户系统性地理解和梳理培训内容
- 使用专业技能完成培训产出（如 PPT 生成）

## 回答规范
1. **结构化输出**：使用标题、分点、表格等 Markdown 格式组织回答，层次清晰
2. **内容聚焦**：只回答用户当前问题，不添加"建议您""下一步""如果您还想了解"等引导性尾巴
3. **专业严谨**：回答、产出都基于文档事实，明确区分文档内容与个人推断，不捏造信息
4. **适度引用**：对文档内容的引用要准确到具体章节或段落
5. **精炼表达**：避免冗余重复，用最少的文字传达最多的信息
6. **纯 Markdown 语法**：禁止使用 HTML 标签（如 <br>、<b>、<ul>），所有格式必须用标准 Markdown 实现（换行用两个空格或空行，列表用 - 或 1.，圆点符号 • 改用 -）

## 场景限定
- 只处理与培训、学习、教育、知识管理相关的请求
- 非培训场景的请求，简要说明不在服务范围内即可，不做过多解释

## 引用规范
引用 rag_search 检索到的文档内容时，在对应内容末尾使用结构化标记：
- 格式：{{ref:文档名|章节或段落描述}}
- 可在一句话末尾连续使用多个标记引用不同来源
- 未使用文档内容时不标注

### 引用位置规则（严格遵守）
- 引用标记必须紧跟在它所引用的观点文本**同一行末尾**，不得另起一行
- 如果是带编号的观点标题，标记放在标题文字末尾：`2. 版本号语义化{{ref:手册|第2章}}`
- 如果是子观点/列表项，标记放在该项文字末尾：`- 采用 AIR 原则{{ref:手册|第3章}}`
- 禁止将引用标记单独放在一行或一个段落的最末尾充当"段落引用"

### 禁止引用的场景（严格遵守）
- **PPT 幻灯片 HTML 内容中严禁出现任何引用标记**（包括 `{{ref:...}}`、`📄 文件名 | 位置`、`ref:文档名|章节` 等一切形式）
- **口播稿文本中严禁出现任何引用标记**
- 引用标记**仅允许在聊天对话文本中使用**，不得带入任何产出物（PPT、口播稿、文件等）
- rag_search 返回的 `📄 文件名 | 章节位置` 是检索来源标注，仅供你在对话中理解内容出处，**绝不能原样写入产出物**

## 技能使用
通过 load_skill 工具查看和加载可用技能。
用户使用 / 命令时（如 /ppt），匹配对应技能并加载执行。
当判断某个技能适用于当前任务时，也应主动加载使用。
"""


class PromptManager:
    """统一管理所有 prompt 模板的构建。"""

    def __init__(self):
        self._viewport_css: str | None = None
        self._style_prompt_template: str | None = None
        self._cover_html_prompt_template: str | None = None

    # ------------------------------------------------------------------
    # Lazy loaders for prompt templates
    # ------------------------------------------------------------------

    def _get_viewport_css(self) -> str:
        if self._viewport_css is None:
            css_path = Path(__file__).resolve().parent.parent.parent / "skills" / "ppt" / "assets" / "viewport-base.css"
            try:
                self._viewport_css = css_path.read_text(encoding="utf-8")
            except FileNotFoundError:
                logger.warning("[PromptManager] viewport-base.css not found at %s", css_path)
                self._viewport_css = "/* viewport-base.css not found */"
        return self._viewport_css

    def _get_style_prompt_template(self) -> str:
        if self._style_prompt_template is None:
            path = _PROMPTS_DIR / "style_prompt.md"
            try:
                self._style_prompt_template = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                logger.warning("[PromptManager] style_prompt.md not found at %s", path)
                self._style_prompt_template = "# ERROR: style_prompt.md not found"
        return self._style_prompt_template

    def _get_cover_html_prompt_template(self) -> str:
        if self._cover_html_prompt_template is None:
            path = _PROMPTS_DIR / "generate_cover_html_prompt.md"
            try:
                self._cover_html_prompt_template = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                logger.warning("[PromptManager] generate_cover_html_prompt.md not found at %s", path)
                self._cover_html_prompt_template = "# ERROR: generate_cover_html_prompt.md not found"
        return self._cover_html_prompt_template

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_style_description_prompt(self, markdown_text: str) -> str:
        """构建风格描述 system prompt。

        Args:
            markdown_text: PPTX 解析后的精准 Markdown 结构报告
        """
        template = self._get_style_prompt_template()
        return (
            f"{template}\n\n"
            f"---\n\n"
            f"## PPTX 结构化解析报告\n\n"
            f"{markdown_text}\n"
        )

    def build_preview_html_prompt(self, style_template: str, resource_base_url: str = "") -> str:
        """构建预览 HTML 生成 system prompt。

        Args:
            style_template: 完整的风格模板 Markdown（即 style_description，含 frontmatter）
            resource_base_url: 图片资源的基础 URL，用于 LLM 在 HTML 中引用图片
        """
        template = self._get_cover_html_prompt_template()
        parts = [
            template,
            "",
            "---",
            "",
            f"=== 图片资源基础 URL ===\n{resource_base_url or '（无外部图片资源，使用本地相对路径）'}",
            "",
            f"=== 风格模版（完整内容，必须严格遵循） ===\n{style_template}",
        ]
        return "\n".join(parts)
