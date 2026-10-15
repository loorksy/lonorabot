import re
from typing import Any

from .registry import installed_registry
from .resolver import SkillSelection, SkillSignals, resolve_skills

# Secondary hints select instructions only. They never route commands or grant authority.
INTENT_HINTS = {
    "memory": r"remember|memory|تتذكر|تذكر|ذاكر|تتذكّر",
    "research": r"research|search|web|statement|ابحث|بحث|بيان|مصادر",
    "market": r"analy[sz]|market|outlook|gold|forex|تحليل|حلل|حلّل|السوق|الذهب|توصية",
    "chart": r"chart|candle|indicator|\b[0-9]+[mhdw]\b|شارت|شموع|مؤشر",
    "trade": r"trade|position|order|buy|sell|صفقة|صفقات|شراء|بيع|أمر|امر|وقف|معلق",
    "watch": r"watch|monitor|راقب|مراقب|تنبيه",
    "goal": r"goal|plan|mission|هدف|خطة|مهمة",
}


def infer_intents(text: str, *, has_goal: bool = False, trigger: str = "user") -> frozenset[str]:
    intents = {name for name, pattern in INTENT_HINTS.items() if re.search(pattern, text, re.I)}
    if "chart" in intents:
        intents.add("market")
    if has_goal:
        intents.add("goal")
    if trigger == "watch":
        intents.update({"watch", "market"})
    return frozenset(intents)


def select_skill_context(
    installed: list[dict[str, Any]],
    signals: SkillSignals,
    known_tools: set[str],
    budget: int = 16000,
) -> SkillSelection:
    registry, rejected = installed_registry(installed, known_tools)
    return resolve_skills(registry, signals, budget, rejected)
