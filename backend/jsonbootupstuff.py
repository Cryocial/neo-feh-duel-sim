import json
from .classes import StatBlock, UtilityBlock
from . import bonusfunctions

STATUS_EFFECT_DATABASE = {}


def initialize_status_database():
    """
    Builds the STATUS_EFFECT_DATABASE by loading 'visualbonuses.json'
    and resolving string references to actual Python functions in 'bonusfunctions.py'.
    """
    try:
        with open("visualbonuses.json", "r") as file:
            data = json.load(file)
    except FileNotFoundError:
        print("Error: 'visualbonuses.json' not found. Status database will be empty.")
        return

    for name, info in data.items():
        combat_stats = StatBlock.from_dict(info.get("combat_stats", {}))
        enemy_combat_stats = StatBlock.from_dict(info.get("enemy_combat_stats", {}))

        util_data = info.get("utilities", {})

        def resolve_logic(logic_name):
            if not logic_name:
                return None
            return getattr(bonusfunctions, logic_name, None)

        utilities = UtilityBlock(
            keywords=util_data.get("keywords", []),
            cooldown_modifiers={
                phase: (resolve_logic(mod) if isinstance(mod, str) else mod)
                for phase, mod in util_data.get("cooldown_modifiers", {}).items()
            },
        )

        if tag := util_data.get("logic_tag"):
            if tag := util_data.get("logic_tag"):
                utilities.truedmg_logic = resolve_logic(tag)
                #ADD MORE SOON

        STATUS_EFFECT_DATABASE[name] = {
            "combat_stats": combat_stats,
            "enemy_combat_stats": enemy_combat_stats,
            "utilities": utilities,
        }


initialize_status_database()
