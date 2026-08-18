"""Visible product identity; internal compatibility names intentionally remain unchanged."""

PRODUCT_NAME = "Years in Focus"
TAGLINE_EN = "A lifetime of photos, aligned in motion."
TAGLINE_DE = "Ein Leben in Bildern – im Fokus der Zeit."


def tagline(language: str) -> str:
    return TAGLINE_EN if language == "en" else TAGLINE_DE
