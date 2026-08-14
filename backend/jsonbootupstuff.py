import json
import os
from .build import StatBlock, Skill, Status, DivineVein
from .constants import MovementType, WeaponType

SKILL_DATABASE: dict[str, Skill] = {}
BONUS_DATABASE: dict[str, Status] = {}
PENALTY_DATABASE: dict[str, Status] = {}
DIVINE_VEINS_DATABASE: dict[str, Status] = {}
UNIT_DATABASE: dict[str, dict] = {}


def _load_statuses(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for name, entry in data.items():
        status = Status(
            name=name,
            type=entry["type"],
            effects=entry.get("effects", []),
            grants_style=entry.get("grants_style", False)
        )
        if status.type == "bonus":
            BONUS_DATABASE[name] = status
        else:
            PENALTY_DATABASE[name] = status


def _load_skills(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for name, entry in data.items():
        visible = entry.get("visible", {})
        SKILL_DATABASE[name] = Skill(
            name=name,
            slot=entry["type"],
            might=visible.get("might", 0),
            slaying=visible.get("slaying", 0),
            cooldown=visible.get("cooldown", 0),
            visible_stats=StatBlock.from_dict(visible.get("grants", {})),
            effects=entry.get("effects", []),
            allowed_movement_types=[
                MovementType[m] for m in entry.get("allowed_movement_types", [])
            ],
            allowed_weapon_types=[
                WeaponType[w] for w in entry.get("allowed_weapon_types", [])
            ],
            is_arcane=entry.get("is_arcane", False),
            is_prf=entry.get("is_prf", False),
            grants_style=entry.get("grants_style", False)
        )


def _load_divine_veins(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for name, entry in data.items():
        DIVINE_VEINS_DATABASE[name] = DivineVein(
            name=name,
            effects=entry.get("effects", [])
        )

def _load_units(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for name, entry in data.items():
        UNIT_DATABASE[name] = entry


def _initialize_databases() -> None:
    base = os.path.dirname(os.path.abspath(__file__))
    loaders = [
        (_load_statuses, "statuses.json"),
        (_load_skills, "skills.json"),
        (_load_units, "units.json"),
        (_load_divine_veins, "divine_veins.json")
    ]
    for loader, filename in loaders:
        path = os.path.join(base, filename)
        try:
            loader(path)
        except FileNotFoundError:
            print(f"{filename} not found.")


_initialize_databases()
