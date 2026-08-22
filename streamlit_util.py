"""
streamlit_app.py

Cascading category -> glass -> drink lookup (same pattern as the original
sushi-roll display_ui), with a dedicated render_drink() function that turns
a DrinkEntry into a readable card instead of dumping raw JSON.

Run with: streamlit run streamlit_app.py
Requires: pip install streamlit pandas
"""

import json

import pandas as pd
import streamlit as st

from drinks import (
    DrinkEntry,
    _ratio_issues,
    fuzzy_search_drinks,
    get_categories,
    get_drink,
    get_drinks_for_glass,
    get_glass_detail,
    get_glass_types,
    parts_to_oz,
    suggest_target_oz,
)


def _title(text: str) -> str:
    return text.replace("_", " ").title()


def render_drink(drink_key: str, drink: DrinkEntry) -> None:
    """Renders a single DrinkEntry as a readable card, skipping empty fields."""
    st.subheader(_title(drink_key))

    # Quick-facts line: type / serving temp / method — only show what's present
    facts = []
    if drink.type:
        facts.append(f"**Type:** {drink.type}")
    if drink.serving_temp:
        facts.append(f"**Serving temp:** {drink.serving_temp}")
    if drink.method:
        facts.append(f"**Method:** {drink.method}")
    if facts:
        st.markdown(" &nbsp;|&nbsp; ".join(facts))

    # Ingredients table — prefer oz (real measurements) over parts (ratio)
    amounts = drink.oz or drink.parts
    if amounts:
        label = "Amounts (oz)" if drink.oz else "Parts (ratio)"
        st.markdown(f"**{label}**")
        df = pd.DataFrame(
            [{"Ingredient": _title(k), "Amount": v} for k, v in amounts.items()]
        )
        st.dataframe(df, hide_index=True, width="stretch")

    # Extras (e.g. mint leaves, cinnamon stick) shown as their own small table
    if drink.extra:
        st.markdown("**Extras**")
        df_extra = pd.DataFrame(
            [{"Item": _title(k), "Amount": v} for k, v in drink.extra.items()]
        )
        st.dataframe(df_extra, hide_index=True, width="stretch")

    col1, col2 = st.columns(2)
    with col1:
        if drink.garnish:
            st.markdown(f"**Garnish**")
            st.write(drink.garnish)
    with col2:
        if drink.tools:
            st.markdown("**Tools**")
            chips = " ".join(f"`{_title(t)}`" for t in drink.tools)
            st.markdown(chips)

    if drink.notes:
        st.info(drink.notes)


def browse_mode() -> None:
    """Original cascading category -> glass -> drink flow."""
    category = st.selectbox(
        "Category",
        get_categories(),
        format_func=_title,
        key="category_select",
    )

    glass_options = get_glass_types(category)
    glass_key = st.selectbox(
        "Glass",
        glass_options,
        format_func=_title,
        key="glass_select",
    )

    drink_options = list(get_drinks_for_glass(category, glass_key).keys())
    if not drink_options:
        st.warning("No drinks found for this glass.")
        return

    drink_key = st.selectbox(
        "Drink",
        drink_options,
        format_func=_title,
        key="drink_select",
    )

    st.divider()

    drink = get_drink(category, glass_key, drink_key)
    if drink:
        render_drink(drink_key, drink)
    else:
        st.warning("Drink not found.")


def search_mode() -> None:
    """Typo-tolerant search: type a query, click a result to render it."""
    query = st.text_input("Search drinks", placeholder="e.g. lyche, martni, moscoe...")

    if not query:
        st.caption("Start typing to search — typos are OK.")
        return

    results = fuzzy_search_drinks(query)

    if not results:
        st.warning(f'No matches for "{query}".')
        return

    st.caption(f"{len(results)} match{'es' if len(results) != 1 else ''}")

    # Build labels like "Lychee Martini — Martini Glass (mixed drinks)"
    labels = [
        f"{_title(r.drink_key)} — {_title(r.glass_key)} ({_title(r.category)})"
        for r in results
    ]

    selected_label = st.radio(
        "Results",
        labels,
        label_visibility="collapsed",
        key=f"search_results_{query}",  # resets selection when the query changes
    )
    selected = results[labels.index(selected_label)]

    st.divider()
    render_drink(selected.drink_key, selected.entry)


def calculator_mode() -> None:
    """
    For a brand-new drink: enter ingredients as a parts ratio, pick a glass,
    and get real oz amounts back — scaled to fit the glass, rounded to a
    practical jigger increment, with a ready-to-paste JSON snippet.
    """
    st.caption(
        "Enter a parts ratio for a new drink and get real oz amounts that fit the glass."
    )

    category = st.selectbox(
        "Category", get_categories(), format_func=_title, key="calc_category"
    )
    glass_key = st.selectbox(
        "Glass", get_glass_types(category), format_func=_title, key="calc_glass"
    )
    glass = get_glass_detail(category, glass_key)
    st.caption(f"{_title(glass.glass)} — capacity {glass.glass_capacity_oz} oz")

    method = st.selectbox(
        "Method",
        ["shaken", "stirred", "built", "blended", "poured"],
        key="calc_method",
    )

    st.markdown("**Ingredients (parts ratio)**")
    parts_df = st.data_editor(
        pd.DataFrame([{"ingredient": "", "parts": 1.0}]),
        num_rows="dynamic",
        width="stretch",
        key="calc_parts_editor",
        column_config={
            "ingredient": st.column_config.TextColumn("Ingredient"),
            "parts": st.column_config.NumberColumn("Parts", min_value=0.0, step=0.25),
        },
    )

    suggested = suggest_target_oz(category, glass_key, method)
    col1, col2 = st.columns(2)
    with col1:
        target_oz = st.number_input(
            "Target total oz",
            min_value=0.5,
            value=float(suggested),
            step=0.25,
            help=f"Suggested {suggested} oz based on {_title(glass.glass)} capacity "
            f"({glass.glass_capacity_oz} oz) and a {method} pour. Override if this "
            f"drink should run lighter or stronger.",
        )
    with col2:
        round_to = st.selectbox("Round to nearest (oz)", [0.25, 0.125, 0.5], index=0)

    if not st.button("Calculate oz", type="primary"):
        return

    parts = {
        str(row["ingredient"]).strip().lower().replace(" ", "_"): row["parts"]
        for _, row in parts_df.iterrows()
        if str(row["ingredient"]).strip() and row["parts"]
    }

    if not parts:
        st.warning("Add at least one ingredient with a parts value.")
        return

    oz = parts_to_oz(parts, target_total_oz=target_oz, round_to=round_to)

    st.markdown("**Calculated oz**")
    df_oz = pd.DataFrame(
        [{"Ingredient": _title(k), "Parts": parts[k], "Oz": oz[k]} for k in parts]
    )
    st.dataframe(df_oz, hide_index=True, width="stretch")

    total = sum(v for v in oz.values() if isinstance(v, (int, float)))
    st.caption(
        f"Total: {total:.2f} oz — target was {target_oz} oz in a {glass.glass_capacity_oz} oz glass"
    )

    # single-entry rounding-drift check, reusing the same logic as validate_parts_oz_consistency
    numeric_parts = {k: v for k, v in parts.items() if isinstance(v, (int, float))}
    numeric_oz = {k: v for k, v in oz.items() if isinstance(v, (int, float))}
    issues = _ratio_issues(
        numeric_parts, numeric_oz, tolerance=0.08, warning_threshold=0.20
    )

    warnings = [msg for sev, msg in issues if sev == "warning"]
    notes = [msg for sev, msg in issues if sev == "note"]

    if warnings:
        st.warning("Possible real ratio issue (not just rounding):")
        for msg in warnings:
            st.caption(f"- {msg}")
    elif notes:
        st.info("Minor rounding drift — expected at small pour sizes, not a problem:")
        for msg in notes:
            st.caption(f"- {msg}")

    st.markdown("**JSON snippet**")
    snippet = {
        "parts": parts,
        "oz": oz,
        "garnish": "",
        "method": method,
        "tools": [],
    }
    st.code(json.dumps(snippet, indent=2), language="json")


def display():
    mode = st.radio(
    "Mode",
    ["Browse", "Search", "Calculator"],
    horizontal=True,
    label_visibility="collapsed",
)

    st.divider()

    if mode == "Browse":
        browse_mode()
    elif mode == "Search":
        search_mode()
    else:
        calculator_mode()

def main() -> None:
    st.set_page_config(page_title="Bartender Reference", page_icon="🍸")
    st.title("🍸 Bartender Reference Lookup")

    mode = st.radio(
        "Mode",
        ["Browse", "Search", "Calculator"],
        horizontal=True,
        label_visibility="collapsed",
    )

    st.divider()

    if mode == "Browse":
        browse_mode()
    elif mode == "Search":
        search_mode()
    else:
        calculator_mode()


if __name__ == "__main__":
    main()
