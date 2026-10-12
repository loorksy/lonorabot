import re


def retrieve_sections(document: str, query: str, limit: int = 6) -> list[str]:
    terms = set(re.findall(r"\w+", query.casefold()))
    sections = re.split(r"(?m)(?=^#{1,3} )", document)
    scored = [
        (len(terms & set(re.findall(r"\w+", section.casefold()))), section) for section in sections
    ]
    return [
        section
        for score, section in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]
        if score
    ]
