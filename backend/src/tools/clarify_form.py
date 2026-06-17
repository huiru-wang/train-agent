import json

from langchain_core.tools import tool
from langgraph.types import interrupt
from pydantic import BaseModel, Field


class FormField(BaseModel):
    name: str = Field(description="字段名")
    label: str = Field(description="显示标签")
    type: str = Field(description="字段类型: text/select/multiselect")
    options: list[str] | None = Field(
        default=None, description="选项列表(select/multiselect时必填)"
    )
    required: bool = Field(default=True)


class ClarifyFormInput(BaseModel):
    title: str = Field(description="表单标题")
    description: str = Field(description="向用户说明为什么需要这些信息")
    fields: list[FormField] = Field(description="表单字段列表")


@tool(args_schema=ClarifyFormInput)
def clarify_form(title: str, description: str, fields: list[dict], **kwargs) -> str:
    """向用户展示一个表单来收集信息。当需要用户澄清意图、选择选项或提供详细参数时使用此工具。
    表单会在前端渲染为交互式UI，用户填写后结果会返回给你。

    重要：
    - 如果返回值包含 cancelled=true，说明用户主动取消了表单，不希望继续当前任务。
      请尊重用户的意愿，礼貌地告知任务已取消，并等待用户的下一步指示。
    - 调用此工具时，请勿在同一条消息中附带说明文字。
      若需要向用户说明为何需要填写信息，请在调用此工具之前单独输出一条文字消息。
    """
    user_response = interrupt({
        "title": title,
        "description": description,
        "fields": fields,
    })

    # User cancelled the form
    if isinstance(user_response, dict) and user_response.get("__cancelled__"):
        return json.dumps({"cancelled": True, "message": "用户取消了表单，不希望继续此任务"}, ensure_ascii=False)

    return json.dumps(user_response, ensure_ascii=False)
