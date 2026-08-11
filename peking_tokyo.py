import json
from pathlib import Path
from collections import defaultdict

from pydantic import BaseModel
import streamlit as st

workspace_path = "./specialty-rolls.json"
absolute_workspace_path = absolute_string = str(Path(workspace_path).expanduser())


class SpecialtyRollsSchema(BaseModel):
    name: str
    isSpicy: bool
    isTempura: bool
    mainFish: str
    ingredients: list[str] = []
    toppings: list[str] = []
    description: str


class SpecialtyRollsResponse(BaseModel):
    rolls: list[SpecialtyRollsSchema]


def get_speciality_rolls():
    with open(absolute_workspace_path) as file:
        loaded_data = json.load(file)
        parsed_rolls = SpecialtyRollsResponse.model_validate(loaded_data)
        mainFish = defaultdict(list)

        for roll in parsed_rolls.rolls:
            for ingredient in roll.ingredients:
                mainFish[ingredient].append(roll.name)

        # print(parsed_rolls.rolls[0].name)
        pretty_json = json.dumps(dict(mainFish), indent=4, sort_keys=True)
        # print(pretty_json)
        st.json(pretty_json, expanded=True, width="stretch")


def display_ui():
    with open(absolute_workspace_path) as file:
        loaded_data = json.load(file)
        parsed_rolls = SpecialtyRollsResponse.model_validate(loaded_data)

        mainFish = defaultdict(list)
        ingredientsDict = defaultdict(list)

        for roll in parsed_rolls.rolls:
            mainFish[roll.name].extend(roll.ingredients)
            for ingredient in roll.ingredients:
                ingredientsDict[ingredient].append(roll.name)

        # by specific item
        roll = st.selectbox("Select a roll", list(mainFish))

        ingredients = {"Ingredients": mainFish[roll]}
        pretty_json = json.dumps(ingredients, indent=4, sort_keys=True)
        st.json(pretty_json, expanded=True)

        # by ingredient
        ingredient = st.selectbox("Select an ingredient", list(ingredientsDict))
        rolls = {"Rolls": ingredientsDict[ingredient]}
        pretty_json = json.dumps(rolls, indent=4, sort_keys=True)
        st.json(pretty_json, expanded=True)
