from pathlib import Path

from src.agent.skill_manager import SkillManager


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "backend" / "skills"


def test_ppt_linked_files_only_include_existing_categories():
    manager = SkillManager(str(SKILLS_DIR))

    linked = manager.list_linked_files("ppt")

    assert "templates" not in linked
    assert "references" in linked
    assert "scripts" in linked
    assert "assets" in linked
    assert "save_and_output.py" in linked["scripts"]
    assert "themes/tokyo-night.css" in linked["assets"]
    assert "animations/animations.css" in linked["assets"]


def test_ppt_load_files_can_read_reference_and_script_files():
    manager = SkillManager(str(SKILLS_DIR))

    files = manager.load_files(
        "ppt",
        ["references/layouts.md", "scripts/save_and_output.py"],
    )

    assert "Layouts catalog" in files["references/layouts.md"]
    assert "Atomically bundle and save PPT HTML output." in files["scripts/save_and_output.py"]
