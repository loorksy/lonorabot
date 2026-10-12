from .loader import load_skill, resources_root


def built_in_skills() -> dict[str, str]:
    root = resources_root() / "skills"
    return {path.parent.name: load_skill(path.parent.name) for path in root.glob("*/SKILL.md")}
