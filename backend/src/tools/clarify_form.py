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
def clarify_form(title: str, description: str, fields: list[dict]) -> str:
    """向用户展示一个表单来收集信息。当需要用户澄清意图、选择选项或提供详细参数时使用此工具。
    表单会在前端渲染为交互式UI，用户填写后结果会返回给你。"""
    # 使用 interrupt 暂停图执行，等待前端用户填写表单后通过 Command(resume=...) 恢复
    user_response = interrupt({
        "title": title,
        "description": description,
        "fields": fields,
    })
    # user_response 是前端传回的表单数据字典
    return f"用户填写的表单结果: {user_response}"
