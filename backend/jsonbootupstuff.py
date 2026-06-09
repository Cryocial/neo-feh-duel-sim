import json
import os
from .classes import StatBlock, UtilityBlock
from . import bonusfunctions

STATUS_EFFECT_DATABASE = {}


def initialize_status_database():
    """
    Builds the STATUS_EFFECT_DATABASE by loading 'visualbonuses.json'
    and resolving string references to actual Python functions in 'bonusfunctions.py'.
    """
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "visualbonuses.json")
        with open(json_path, "r") as file:
            data = json.load(file)
    except FileNotFoundError:
        print(f"Error: 'visualbonuses.json' not found at {json_path}. Status database will be empty.")
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
            utilities.truedmg_logic = resolve_logic(tag)

        if tag := util_data.get("truedr_logic_tag"):
            utilities.truedr_logic = resolve_logic(tag)

        if tag := util_data.get("predmg_tag"):
            utilities.predmg_logic = resolve_logic(tag)

        if tag := util_data.get("heal_start_tag"):
            utilities.heal_precombat_logic = resolve_logic(tag)

        if tag := util_data.get("heal_hit_tag"):
            utilities.heal_on_hit_logic = resolve_logic(tag)

        if tag := util_data.get("heal_after_tag"):
            utilities.heal_after_logic = resolve_logic(tag)
        if tag := util_data.get("set_to_one_tag"):
            utilities.set_to_one_logic = resolve_logic(tag)
        if tag := util_data.get("adaptive_tag"):
            utilities.adaptive_logic = resolve_logic(tag)
        if tag := util_data.get("first_hit_dmg_floor_tag"):
            utilities.first_hit_dmg_floor_logic = resolve_logic(tag)
        if tag := util_data.get("dmg_floor_tag"):
            utilities.dmg_floor_logic = resolve_logic(tag)
            # ADD MORE SOON

        STATUS_EFFECT_DATABASE[name] = {
            "combat_stats": combat_stats,
            "enemy_combat_stats": enemy_combat_stats,
            "utilities": utilities,
        }


initialize_status_database()
