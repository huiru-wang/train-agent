import logging

from langchain_core.tools import tool

from src.agent.skill_manager import SkillManager

logger = logging.getLogger(__name__)


def create_load_skill_tool(skill_manager: SkillManager):
    """Create the load_skill tool with dynamic docstring listing available skills.

    Follows the LangChain Skills pattern: a single tool whose docstring
    contains all available skill names + descriptions. Agent sees the list
    via the tool schema and loads on-demand.
    """
    available = skill_manager.list_skills()
    skill_list = "\n".join(
        f"    - {s['name']}: {s['description']}" for s in available
    )

    # Build reference info for skills that have references
    ref_info_parts = []
    for skill in available:
        refs = skill_manager.list_references(skill["name"])
        if refs:
            ref_names = ", ".join(refs)
            ref_info_parts.append(
                f"    {skill['name']} references: {ref_names}"
            )
    ref_info = "\n".join(ref_info_parts)

    dynamic_description = f"""Load a specialized skill prompt, or a specific reference document within a skill.

Available skills:
{skill_list if skill_list else '    (no skills registered)'}

{('Reference documents (use reference_name to load):\n' + ref_info) if ref_info else ''}

When called without reference_name, returns the skill's main prompt.
When called with reference_name (e.g. "themes.md"), returns that reference document."""

    @tool(description=dynamic_description)
    def load_skill(skill_name: str, reference_name: str = "") -> str:
        """Load a skill prompt or its reference document.

        Args:
            skill_name: Name of the skill to load.
            reference_name: Optional. Name of a reference file (e.g. "themes.md").
                          If provided, loads that reference instead of the main skill.
        """
        if reference_name:
            logger.info(
                "[Tool:load_skill] loading reference: skill=%s, ref=%s",
                skill_name, reference_name,
            )
            # Normalize: accept both "themes.md" and "references/themes.md"
            ref_path = reference_name
            if not ref_path.startswith("references/"):
                ref_path = f"references/{ref_path}"
            content = skill_manager.load_reference(skill_name, ref_path)
            if content is None:
                available_refs = skill_manager.list_references(skill_name)
                logger.warning(
                    "[Tool:load_skill] reference not found: skill=%s, ref=%s, available=%s",
                    skill_name, reference_name, available_refs,
                )
                return (
                    f"Reference '{reference_name}' not found for skill '{skill_name}'. "
                    f"Available: {', '.join(available_refs) if available_refs else 'none'}"
                )
            logger.info(
                "[Tool:load_skill] reference loaded: skill=%s, ref=%s, %d chars",
                skill_name, reference_name, len(content),
            )
            return content

        logger.info("[Tool:load_skill] loading skill: %s", skill_name)
        content = skill_manager.load_skill(skill_name)
        if content is None:
            available_names = [s["name"] for s in skill_manager.list_skills()]
            logger.warning(
                "[Tool:load_skill] skill not found: %s, available=%s",
                skill_name, available_names,
            )
            return f"Skill '{skill_name}' not found. Available: {', '.join(available_names)}"

        # Substitute ${SKILL_DIR} with actual skill directory path
        from pathlib import Path
        skill_dir = str(Path(skill_manager._skills[skill_name].file_path).parent)
        content = content.replace("${SKILL_DIR}", skill_dir)

        logger.info(
            "[Tool:load_skill] skill loaded: %s, %d chars, skill_dir=%s",
            skill_name, len(content), skill_dir,
        )
        return content

    return load_skill
