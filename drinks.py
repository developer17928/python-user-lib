"""
drinks.py

Parsing + query layer over bartender_drinks_reference.json.
Mirrors the logic in src/lib/drinks.ts, but framework-agnostic Python —
usable from a script, a notebook, a CLI, or wired into a Flask/FastAPI
route later, same as the TS version can sit behind Astro API routes.

Usage:
    from drinks import (
        get_categories, get_glass_types, get_glass_detail,
        get_drinks_for_glass, get_drink, get_all_drinks_flat, search_drinks
    )

    print(get_categories())
    print(get_glass_types("mixed_drinks"))
    print(get_drink("mixed_drinks", "martini_glass", "lychee_martini"))
    print(search_drinks("lychee"))
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

Category = str  # "mixed_drinks" | "wine" | "sake"

# Adjust this if you place the JSON somewhere else, or set the
# DRINKS_DATA_PATH environment variable to override at runtime.
workspace_path = "../../api/drinks-pk.json"
DEFAULT_DATA_PATH = Path(absolute_workspace_path) = absolute_string = str(Path(workspace_path).expanduser())
# DEFAULT_DATA_PATH = Path(
#     os.environ.get(
#         "DRINKS_DATA_PATH",
#         Path(__file__).resolve().parent.parent / "api" / "drinks-pk.json",
#     )
# )


@dataclass
class DrinkEntry:
    parts: Optional[Dict[str, Union[int, float, str]]] = None
    oz: Optional[Dict[str, Union[int, float, str]]] = None
    extra: Optional[Dict[str, Union[int, float, str]]] = None
    garnish: Optional[str] = None
    method: Optional[str] = None
    tools: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    type: Optional[str] = None
    serving_temp: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DrinkEntry":
        return cls(
            parts=data.get("parts"),
            oz=data.get("oz"),
            extra=data.get("extra"),
            garnish=data.get("garnish"),
            method=data.get("method"),
            tools=data.get("tools", []),
            notes=data.get("notes"),
            type=data.get("type"),
            serving_temp=data.get("serving_temp"),
        )


@dataclass
class GlassEntry:
    glass: str
    glass_capacity_oz: Union[int, float]
    drinks: Dict[str, DrinkEntry]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlassEntry":
        return cls(
            glass=data["glass"],
            glass_capacity_oz=data["glass_capacity_oz"],
            drinks={
                key: DrinkEntry.from_dict(val) for key, val in data["drinks"].items()
            },
        )


@dataclass
class FlatDrink:
    category: Category
    glass_key: str
    glass_name: str
    drink_key: str
    entry: DrinkEntry


_cache: Optional[Dict[Category, Dict[str, GlassEntry]]] = None


def _load_data(path: Path = DEFAULT_DATA_PATH) -> Dict[Category, Dict[str, GlassEntry]]:
    """Loads and parses the JSON once, then serves from an in-memory cache."""
    global _cache
    if _cache is not None:
        return _cache

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as err:
        raise FileNotFoundError(
            f'Could not read drinks data at "{path}". '
            f"Set DRINKS_DATA_PATH or move the JSON there. Original error: {err}"
        ) from err

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as err:
        raise ValueError(f'Drinks JSON at "{path}" is not valid JSON: {err}') from err

    _cache = {
        category: {
            glass_key: GlassEntry.from_dict(glass_val)
            for glass_key, glass_val in glasses.items()
        }
        for category, glasses in parsed.items()
    }
    return _cache


def clear_drinks_cache() -> None:
    """Call this if the JSON changes on disk and you want to force a re-read."""
    global _cache
    _cache = None


def get_categories() -> List[Category]:
    return list(_load_data().keys())


def is_valid_category(category: str) -> bool:
    return category in get_categories()


def get_glass_types(category: Category) -> List[str]:
    data = _load_data()
    return list(data.get(category, {}).keys())


def get_glass_detail(category: Category, glass_key: str) -> Optional[GlassEntry]:
    data = _load_data()
    return data.get(category, {}).get(glass_key)


def get_drinks_for_glass(category: Category, glass_key: str) -> Dict[str, DrinkEntry]:
    glass = get_glass_detail(category, glass_key)
    return glass.drinks if glass else {}


def get_drink(
    category: Category, glass_key: str, drink_key: str
) -> Optional[DrinkEntry]:
    return get_drinks_for_glass(category, glass_key).get(drink_key)


def get_all_drinks_flat() -> List[FlatDrink]:
    """Flattens the whole dataset into one list — handy for search and 'browse all' views."""
    data = _load_data()
    out: List[FlatDrink] = []

    for category, glasses in data.items():
        for glass_key, glass_entry in glasses.items():
            for drink_key, drink in glass_entry.drinks.items():
                out.append(
                    FlatDrink(
                        category=category,
                        glass_key=glass_key,
                        glass_name=glass_entry.glass,
                        drink_key=drink_key,
                        entry=drink,
                    )
                )
    return out


def _searchable_tokens(flat: FlatDrink) -> List[str]:
    """Breaks a drink's searchable fields into individual lowercase words/tokens."""
    e = flat.entry
    ingredient_names = list((e.parts or e.oz or {}).keys())
    fields = [
        flat.drink_key,
        flat.glass_name,
        e.method or "",
        e.type or "",
        e.notes or "",
        *e.tools,
        *ingredient_names,
    ]
    # split on underscores/spaces so "lychee_martini" -> ["lychee", "martini"]
    tokens: List[str] = []
    for field_val in fields:
        tokens.extend(field_val.lower().replace("_", " ").split())
    return tokens


def search_drinks(query: str) -> List[FlatDrink]:
    """
    Exact, case-insensitive substring search across drink name, glass name,
    method, type, notes, tools, and ingredient names (from parts/oz).
    For typo-tolerant search, use fuzzy_search_drinks instead.
    """
    q = query.strip().lower()
    if not q:
        return []

    results: List[FlatDrink] = []
    for flat in get_all_drinks_flat():
        haystack = " ".join(_searchable_tokens(flat))
        if q in haystack:
            results.append(flat)

    return results


def fuzzy_search_drinks(query: str, threshold: float = 0.72) -> List[FlatDrink]:
    """
    Typo-tolerant search. Exact substring matches always rank first (score 1.0);
    anything else is scored by how closely the query matches individual words
    in the drink's searchable fields, using difflib's SequenceMatcher ratio.

    threshold: minimum similarity (0-1) for a fuzzy (non-exact) match to count.
               0.72 is a reasonable default — catches single-letter typos and
               small transpositions without matching unrelated words.
    """
    from difflib import SequenceMatcher

    q = query.strip().lower()
    if not q:
        return []

    scored: List[tuple] = []  # (score, FlatDrink)

    for flat in get_all_drinks_flat():
        tokens = _searchable_tokens(flat)
        haystack = " ".join(tokens)

        if q in haystack:
            scored.append((1.0, flat))
            continue

        # best similarity between the query and any single token
        best = max(
            (SequenceMatcher(None, q, tok).ratio() for tok in tokens), default=0.0
        )
        if best >= threshold:
            scored.append((best, flat))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [flat for _, flat in scored]


def parts_to_oz(
    parts: Dict[str, Union[int, float, str]],
    target_total_oz: float,
    round_to: float = 0.25,
) -> Dict[str, Union[float, str]]:
    """
    Scales a `parts` ratio to real ounces that sum to (approximately)
    target_total_oz, preserving the ratio between ingredients.

    Non-numeric entries (e.g. "2 dashes" for bitters) are passed through
    unscaled — dashes aren't a volume ratio and shouldn't be blended into
    the total.

    round_to: rounds each scaled amount to the nearest practical jigger
              increment (0.25 oz by default; use 0.125 for finer control).
              Rounding means the final sum may be off from target_total_oz
              by a small amount — that's expected and fine in practice.

    Example:
        >>> parts_to_oz({"vodka": 3, "lychee_liqueur": 2, "lychee_juice": 1}, target_total_oz=4)
        {'vodka': 2.0, 'lychee_liqueur': 1.25, 'lychee_juice': 0.75}
    """
    numeric_parts = {k: v for k, v in parts.items() if isinstance(v, (int, float))}
    non_numeric = {k: v for k, v in parts.items() if not isinstance(v, (int, float))}

    total_parts = sum(numeric_parts.values())
    if total_parts <= 0:
        raise ValueError("parts must contain at least one positive numeric value")

    scale = target_total_oz / total_parts

    result: Dict[str, Union[float, str]] = {}
    for k, v in numeric_parts.items():
        raw = v * scale
        rounded = round(raw / round_to) * round_to
        result[k] = round(rounded, 3)

    # non-numeric entries (bitters dashes, etc.) pass through as-is
    result.update(non_numeric)
    return result


def suggest_target_oz(
    category: Category, glass_key: str, method: str = "shaken"
) -> float:
    """
    Suggests a target total oz for a new drink based on the glass's
    capacity and how the drink is served.

    "Up" drinks (shaken/stirred, strained into an empty glass — no ice in
    the final glass) can fill most of the glass, so this targets ~80% of
    capacity. Built drinks served over ice lose 40-50% of the glass to the
    ice itself, so this targets ~55% of capacity for the liquid alone.
    Blended drinks (frozen, no separate ice) target ~90%, since the ice is
    part of the measured volume.

    This is a starting point, not a rule — override it in the UI/CLI if a
    particular drink calls for something different.
    """
    glass = get_glass_detail(category, glass_key)
    if not glass:
        raise ValueError(f'Unknown glass "{glass_key}" in category "{category}"')

    method_normalized = (method or "").lower()
    if "built" in method_normalized:
        fill_ratio = 0.55
    elif "blend" in method_normalized:
        fill_ratio = 0.90
    else:  # shaken, stirred, poured, and anything else served "up"
        fill_ratio = 0.80

    return round(glass.glass_capacity_oz * fill_ratio, 2)


@dataclass
class ConsistencyIssue:
    category: Category
    glass_key: str
    drink_key: str
    detail: str
    severity: (
        str  # "note" (likely rounding noise) | "warning" (likely a real ratio error)
    )


def _ratio_issues(
    numeric_parts: Dict[str, float],
    numeric_oz: Dict[str, float],
    tolerance: float,
    warning_threshold: float,
) -> List[tuple]:
    """
    Compares every shared ingredient's ratio-to-baseline in parts vs. oz.
    Returns (severity, message) tuples for anything outside `tolerance`.

    Two severities, not one, because small-volume drinks legitimately drift
    by 10-20% just from rounding to a practical jigger increment (e.g. a
    4 oz drink split 6 ways means each "part" is 0.67 oz — rounding that to
    the nearest 0.25 oz moves the ratio by double digits without any actual
    mistake). Below `warning_threshold` that's flagged as a "note" — worth
    glancing at, not worth chasing. At or above it, it looks like an actual
    error (e.g. parts said 3:2:1 but oz said 2:1:1) and is flagged as a
    "warning".
    """
    issues: List[tuple] = []
    shared = set(numeric_parts) & set(numeric_oz)
    if len(shared) < 2:
        return issues

    baseline = sorted(shared)[0]
    if numeric_parts[baseline] == 0 or numeric_oz[baseline] == 0:
        return issues

    for ing in sorted(shared - {baseline}):
        part_ratio = numeric_parts[ing] / numeric_parts[baseline]
        oz_ratio = numeric_oz[ing] / numeric_oz[baseline]
        if part_ratio == 0:
            continue

        relative_diff = abs(oz_ratio - part_ratio) / part_ratio
        if relative_diff <= tolerance:
            continue

        severity = "warning" if relative_diff >= warning_threshold else "note"
        issues.append(
            (
                severity,
                f"ratio drift: parts say {ing}:{baseline} = {part_ratio:.2f}, "
                f"oz says {oz_ratio:.2f} ({relative_diff:.0%} off)",
            )
        )

    return issues


def validate_parts_oz_consistency(
    tolerance: float = 0.08,
    warning_threshold: float = 0.20,
) -> List[ConsistencyIssue]:
    """
    Scans every drink that has both `parts` and `oz` and checks whether the
    oz values preserve the same ratio as the parts values. Flags entries
    where they've drifted apart (as with the original PT lychee martini
    bug, where parts implied 3:2:1 but oz was actually 2:1:1).

    Only numeric values are compared; ingredients only present in one of
    the two dicts, or with non-numeric values (bitters dashes), are skipped
    for ratio purposes but reported if one side is missing an ingredient
    the other has — some of those are intentional (e.g. a drink split
    across two vessels, or a "topped up" ingredient with no parts
    equivalent), so treat "missing" reports as informational, not bugs.

    tolerance: below this relative difference, no issue is reported at all.
    warning_threshold: at or above this, an issue is a "warning" (likely a
                        real ratio error). Between tolerance and this, it's
                        a "note" (likely just rounding noise from jigger
                        increments on a small pour — see _ratio_issues).
    """
    issues: List[ConsistencyIssue] = []

    for flat in get_all_drinks_flat():
        parts = flat.entry.parts
        oz = flat.entry.oz
        if not parts or not oz:
            continue

        numeric_parts = {k: v for k, v in parts.items() if isinstance(v, (int, float))}
        numeric_oz = {k: v for k, v in oz.items() if isinstance(v, (int, float))}

        missing_in_oz = set(numeric_parts) - set(numeric_oz)
        missing_in_parts = set(numeric_oz) - set(numeric_parts)

        if missing_in_oz:
            issues.append(
                ConsistencyIssue(
                    flat.category,
                    flat.glass_key,
                    flat.drink_key,
                    f"in parts but missing from oz: {sorted(missing_in_oz)}",
                    severity="note",
                )
            )
        if missing_in_parts:
            issues.append(
                ConsistencyIssue(
                    flat.category,
                    flat.glass_key,
                    flat.drink_key,
                    f"in oz but missing from parts: {sorted(missing_in_parts)}",
                    severity="note",
                )
            )

        for severity, detail in _ratio_issues(
            numeric_parts, numeric_oz, tolerance, warning_threshold
        ):
            issues.append(
                ConsistencyIssue(
                    flat.category, flat.glass_key, flat.drink_key, detail, severity
                )
            )

    return issues


if __name__ == "__main__":
    # Quick manual smoke test / CLI-style lookup, e.g.:
    #   python drinks.py search lychee
    #   python drinks.py drink mixed_drinks martini_glass lychee_martini
    #   python drinks.py validate
    import sys

    args = sys.argv[1:]

    if not args:
        print("Categories:", get_categories())
    elif args[0] == "search" and len(args) == 2:
        for r in search_drinks(args[1]):
            print(f"{r.category}/{r.glass_key}/{r.drink_key}")
    elif args[0] == "fuzzy" and len(args) == 2:
        for r in fuzzy_search_drinks(args[1]):
            print(f"{r.category}/{r.glass_key}/{r.drink_key}")
    elif args[0] == "drink" and len(args) == 4:
        _, category, glass_key, drink_key = args
        print(get_drink(category, glass_key, drink_key))
    elif args[0] == "validate":
        found = validate_parts_oz_consistency()
        if not found:
            print("No parts/oz inconsistencies found.")
        for issue in found:
            print(
                f"[{issue.category}/{issue.glass_key}/{issue.drink_key}] {issue.detail}"
            )
    else:
        print("Usage:")
        print("  python drinks.py")
        print("  python drinks.py search <query>")
        print("  python drinks.py fuzzy <query>")
        print("  python drinks.py drink <category> <glass_key> <drink_key>")
        print("  python drinks.py validate")
