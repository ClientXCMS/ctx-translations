"""Daily ceiling on the volume sent to a translation engine.

Cloudflare Workers AI has no spending cap of its own, and a large one-off
backlog (or a bug looping on the same keys) could otherwise burn through a
free allowance in a single run. The count lives in a JSON file committed
alongside the translations, keyed by day: losing it costs at most one day's
ceiling, which is the same order as the allowance resetting anyway.
"""

import json
import os
from datetime import date

# Cloudflare Workers AI pricing for @cf/meta/m2m100-1.2b, checked against
# https://developers.cloudflare.com/workers-ai/platform/pricing/ on 2026-09-20:
# $0.011 per 1,000 neurons, 31,050 neurons per million tokens (in+out combined),
# 10,000 neurons/day free. ~4 characters per token is a rough estimate for
# latin-alphabet languages (Cloudflare does not publish a Python tokenizer for
# this model), good enough to size a decision, not to bill down to the cent.
CHARACTERS_PER_TOKEN = 4
NEURONS_PER_MILLION_TOKENS = 31_050
FREE_NEURONS_PER_DAY = 10_000
USD_PER_1000_NEURONS = 0.011


def estimate_cost_usd(characters: int) -> float:
    """Rough $ cost to translate this many source characters into one target language.

    Doubles the token estimate for the output side: the model both reads and
    writes tokens, and a translation is usually close in length to its source.
    """
    tokens = (characters / CHARACTERS_PER_TOKEN) * 2
    neurons = (tokens / 1_000_000) * NEURONS_PER_MILLION_TOKENS
    billable_neurons = max(0.0, neurons - FREE_NEURONS_PER_DAY)
    return (billable_neurons / 1000) * USD_PER_1000_NEURONS


class TranslationBudget:
    def __init__(self, path: str, daily_character_budget: int, force: bool = False):
        self.path = path
        self.daily_character_budget = daily_character_budget
        self.force = force
        self.state = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {"date": str(date.today()), "characters_used": 0}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"date": str(date.today()), "characters_used": 0}
        if data.get("date") != str(date.today()):
            return {"date": str(date.today()), "characters_used": 0}
        return data

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def allows(self, characters: int) -> bool:
        if self.daily_character_budget <= 0 and not self.force:
            return False
        if self.force or self.state["characters_used"] + characters <= self.daily_character_budget:
            return True
        estimated_cost = estimate_cost_usd(characters)
        print(
            f"Daily translation budget reached "
            f"({self.state['characters_used']}/{self.daily_character_budget} characters). "
            f"Translating this key would cost an estimated ${estimated_cost:.4f}. "
            "Re-run with force_translation_budget to proceed anyway."
        )
        return False

    def spend(self, characters: int) -> None:
        self.state["characters_used"] += characters
