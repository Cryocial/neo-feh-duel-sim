# Architecture Documentation — FEH Combat Simulator

## Table of Contents
1. [Overview](#overview)
2. [Startup Loading](#startup-loading)
3. [Core Classes](#core-classes)
4. [Condition System](#condition-system)
5. [JSON Parsing](#json-parsing)
6. [User Flow](#user-flow)
7. [Simulation Timeline](#simulation-timeline)

---

## Overview

```
JSON (skills, statuses, units)
        │
        │  read at startup
        ▼
In-memory databases: SKILL_DATABASE, BONUS_DATABASE, PENALTY_DATABASE, UNIT_DATABASE
        │
        │  user builds teams
        ▼
Unit instances (with Skill in each slot, Status in active_statuses)
        │
        │  simulation start
        ▼
CombatantState (with 6 lists of Effect instances created from Skills and Statuses)
        │
        │  phase-by-phase simulation
        ▼
Result: final HP of both units
```

---

## Startup Loading

At application startup, three JSON files are read and stored in memory:

```python
SKILL_DATABASE:    dict[str, Skill]    # indexed by skill name
BONUS_DATABASE:    dict[str, Status]   # bonus-type statuses, indexed by name
PENALTY_DATABASE:  dict[str, Status]   # penalty-type statuses, indexed by name
UNIT_DATABASE:     dict[str, dict]     # raw data, indexed by unit name
```

`BONUS_DATABASE` and `PENALTY_DATABASE` are both fed from a single status JSON file, with entries routed according to their `type` field.

`Skill` and `Status` are instantiated at startup because they are fully defined by the JSON, with no user input. They are declared `frozen=True` to prevent accidental mutation.

`Unit` is not instantiated at startup because a unit requires user choices (IVs, merges, dragonflowers, etc.) that are not known in advance. `UNIT_DATABASE` only holds raw data (base stats, movement type, color, etc.). If we used a database of `Unit` instances and the user wanted to pit the same unit against itself with different merge counts, we would inevitably need two `Unit` instances, which would force us to copy the object stored in the database — not a clean design.

If two units equip the same skill, they share a reference to the same `Skill` object in memory. This is safe because `Skill` is immutable — it is never modified, only read.

---

## Core Classes

### `Effect` and `EffectType`

An `Effect` represents an atomic behavior applied to one of the two units during combat: stat boost, damage reduction, follow-up neutralization, bonus damage, etc. Each skill or status can carry multiple effects. An `EffectType` is an enum that identifies the nature of the effect and determines how the simulator will interpret it.

In the skill and status JSON files, each effect is encoded as a dictionary that ALWAYS contains the following keys:

- `"effect"` to describe the effect type
- `"target"` : `"self"` or `"foe"`. Used **only during construction** of `Effect` objects at simulation startup: it indicates which unit's `CombatantState` should receive the effect. Once distributed, `"target"` is no longer retained — it is not a field of the `Effect` class. (For example, if conditions are met, both the "Foe cannot make a follow-up attack" effect and the "Lancebreaker 3" skill distribute the `EffectType.FU_DENY` effect into the foe's `CombatantState`, while "Windsweep 3" distributes it into the unit's own `CombatantState`.)
- `"params"` are parameters specific to the effect type. For example, an `EffectType.PENALTY_NEUT` effect has no parameters so `params = {}` — the simulator will compute the stat penalties to neutralize on its own. An effect like `EffectType.PERC_DR_STRIKE`, however, must specify the reduction percentage and which strikes it applies to. If the effect comes from "Remote Sparrow" then `params = { "formula": "", "multiplier": 0, "flat": 30, "min": 30, "max": 30, "strike": "every_strike", "piercable": True }`, but if it comes from "Guard Echo" then `params = { "formula": "", "multiplier": 0, "flat": 20, "min": 20, "max": 20, "strike": "every_strike", "piercable": True }`
- `"conditions"` describes the activation conditions for the effect (see the [Condition System](#condition-system) section)

At simulation start, the `effects` lists of the equipped `Skill` and `Status` objects are iterated and each dictionary is transformed into an `Effect` instance:

```python
@dataclass
class Effect:
    type:       EffectType
    applied_by: Literal["bonus", "penalty", "self", "foe", "ally", "enemy"]
    params:     dict
    conditions: list[Condition]
```

`applied_by` tracks the **source** of the effect, not its target: `"bonus"` if the effect comes from a bonus status, `"penalty"` from a penalty status, `"self"` from the unit's own skill, `"foe"` from the opponent's skill, `"ally"` from an ally, `"enemy"` from an enemy. This information is useful for example in bonus or penalty neutralization effects.

---

### `Skill`

```python
@dataclass(frozen=True)
class Skill:
    name:                    str
    slot:                    str
    might:                   int                    # base weapon damage (contributes to visible ATK)
    slaying:                 int                    # visible cooldown reduction in the build
    cooldown:                int
    visible_stats:           StatBlock              # visible bonuses on the stats screen
    effects:                 list[dict]             # raw effect definitions from the JSON
    allowed_movement_types:  list[MovementType]     # empty list = no restriction
    allowed_weapon_types:    list[WeaponType]       # empty list = no restriction
    is_arcane:               bool = False           # bypasses prf restrictions
    is_prf:                  bool = False           # only certain units can equip it
```

**JSON encoding example for a skill:**

*Arcane Cake:*
>Might 16 Rng 1\
>Accelerates Special trigger (cooldown count-1).
>
>[...]
>
>Grants Atk/Spd/Def/Res+15 to unit, unit deals +25 damage (excluding area-of-effect Specials), reduces damage from foe's attacks by 15 (excluding area-of-effect Specials), reduces damage from foe's Specials by an additional 15 (excluding area-of-effect Specials), and reduces the percentage of foe's non-Special "reduce damage by X%" skills by 50% during combat (excluding area-of-effect Specials).

```json
"Arcane Cake": {
  "type": "weapon",
  "visible": {
    "might": 16,
    "range": 1,
    "slaying": 1,
    "grants": {}
  },
  "allowed_movement_types": [],
  "allowed_weapon_types": ["AXE"],
  "is_arcane": true,
  "is_prf": false,
  "effects": [
    { "effect": "STAT_BOOST",
      "target": "self",
      "params": {
        "stats": ["atk", "spd", "defense", "res"],
        "formula": "",
        "multiplier": 0,
        "flat": 15,
        "min": 15,
        "max": 15
      },
      "conditions": []
    },
    { "effect": "FLAT_DAMAGE_STRIKE",
      "target": "self",
      "params": {
        "formula": "",
        "multiplier": 0,
        "flat": 25,
        "min": 25,
        "max": 25,
        "strike": "every_strike"
      },
      "conditions": []
    },
    { "effect": "FLAT_DR_STRIKE",
      "target": "self",
      "params": {
        "formula": "",
        "multiplier": 0,
        "flat": 15,
        "min": 15,
        "max": 15,
        "strike": "every_strike"
      },
      "conditions": []
    },
    { "effect": "FLAT_DR_STRIKE",
      "target": "self",
      "params": {
        "formula": "",
        "multiplier": 0,
        "flat": 15,
        "min": 15,
        "max": 15,
        "strike": "on_special"
      },
      "conditions": []
    },
    { "effect": "DR_PIERCE",
      "target": "self",
      "params": {
        "value": 50,
        "strike": "every_strike"
      },
      "conditions": []
    }
  ]
}
```

*Nightmare Staff:*
>Might 14 Rng 2\
>Accelerates Special trigger (cooldown count-1).
>
>[...]
>
>At start of combat, if unit's HP ≥ 25%, grants bonus to unit's Atk/Spd/Def/Res = number of foes within 3 rows or 3 columns centered on unit × 3, + 5 (max 14), grants bonus to unit's Atk = max Special cooldown count value × 4, and reduces damage from foe's attacks by 20% of unit's Spd during combat (excluding area-of-effect Specials), and also, if unit's Spd > foe's Spd, foe cannot trigger Specials during combat (excluding area-of-effect Specials).

```json
"Nightmare Staff": {
  "type": "weapon",
  "visible": {
    "might": 14,
    "range": 2,
    "slaying": 1,
    "grants": {}
  },
  "allowed_movement_types": [],
  "allowed_weapon_types": ["COLORLESS_TOME"],
  "is_arcane": false,
  "is_prf": true,
  "effects": [
    {
      "effect": "STAT_BOOST",
      "target": "self",
      "params": {
        "stats": ["atk", "spd", "defense", "res"],
        "formula": "3R3C_foes",
        "multiplier": 3,
        "flat": 5,
        "min": 5,
        "max": 14,
        "unit": "self"
      },
      "conditions": [
        {
          "type": "hp_above_pct", 
          "params": {
            "unit": "self",
            "threshold": 25
          }
        }
      ]
    },
    {
      "effect": "STAT_BOOST",
      "target": "self",
      "params": {
        "stats": ["atk"],
        "formula": "max_cooldown",
        "multiplier": 4,
        "flat": 0,
        "min": 0,
        "max": -1,
        "unit": "self"
      },
      "conditions": [
        {
          "type": "hp_above_pct", 
          "params": {
            "unit": "self",
            "threshold": 25
          }
        }
      ]
    },
    {
      "effect": "FLAT_DR_STRIKE",
      "target": "self",
      "params": {
        "formula": "cbt_stat",
        "multiplier": 0.20,
        "flat": 0,
        "min": 0,
        "max": -1,
        "unit": "self",
        "stat": "spd",
        "strike": "every_strike"
      },
      "conditions": [
        {
          "type": "hp_above_pct", 
          "params": {
            "unit": "self",
            "threshold": 25
          }
        }
      ]
    },
    {
      "effect": "SPECIAL_TRIGGER_NEUT",
      "target": "foe",
      "params": {},
      "conditions": [
        {
          "type": "hp_above_pct", 
          "params": {
            "unit": "self",
            "threshold": 25
          }
        },
        { 
          "type": "cbt_stat_check",
          "params": {
            "stat": "spd",
            "margin": 0
          }
        }
      ]
    }
  ]
}
```

---

### `Status`

```python
@dataclass(frozen=True)
class Status:
    name:    str
    type:    Literal["bonus", "penalty"]
    effects: list[dict]     # raw effect definitions from the JSON
```

**JSON encoding example for a status:**

*Change of Fate:*
>Grants Atk/Spd/Def/Res+5 to unit and unit deals damage = 3 × the total of the number of Bonus and Penalty effects active on unit, excluding stat bonuses and stat penalties, during combat (max 15; including area-of-effect Specials).

```json
"Change of Fate": {
  "type": "bonus",
  "effects": [
    { "effect": "STAT_BOOST",
      "target": "self",
      "params": {
        "stats": ["atk", "spd", "defense", "res"],
        "formula": "",
        "multiplier": 0,
        "flat": 5,
        "min": 5,
        "max": 5
      },
      "conditions": []
    },
    { "effect": "FLAT_DAMAGE_AOE",
      "target": "self",
      "params": {
        "formula": "num_bonus_and_penalties",
        "multiplier": 3,
        "flat": 0,
        "min": 0,
        "max": 15,
        "unit": "self"
      },
      "conditions": []
    },
    { "effect": "FLAT_DAMAGE_STRIKE",
      "target": "self",
      "params": {
        "formula": "num_bonus_and_penalties",
        "multiplier": 3,
        "flat": 0,
        "min": 0,
        "max": 15,
        "unit": "self",
        "strike": "every_strike"
      },
      "conditions": []
    }
  ]
}
```

---

### `Unit`

Created from `UNIT_DATABASE` data and user choices. Contains only build information. Combat-specific information is stored in `CombatantState`.

```python
class Unit:
    name:             str
    movement_type:    MovementType
    weapon_type:      WeaponType
    color:            Color
    base_stats:       StatBlock
    dragonflower:     int
    merges:           int
    boon:             str | None
    bane:             str | None
    floret:           str | None
    superboon:        list[str]
    superbane:        list[str]
    weapon:           Skill | None
    special:          Skill | None
    a_slot:           Skill | None
    b_slot:           Skill | None
    c_slot:           Skill | None
    s_slot:           Skill | None
    x_slot:           Skill | None
    prf_skills:       list[str]      # names of prf skills equippable by this unit (from UNIT_DATABASE)
    active_statuses:  list[Status]
    visible_buffs:    StatBlock
    visible_debuffs:  StatBlock
    max_cooldown:     int           # computed from the equipped Special and slaying effects
    pre_charge:       int           # cooldown reduction chosen by the user before combat
```

---

### `CombatantState`

At the start of a combat simulation, two `CombatantState` instances are created. They hold the current combat state of a unit with information that evolves throughout it. This includes current HP, the Special cooldown, and the 6 effect lists that drive the simulation.

```python
@dataclass
class CombatantState:
    unit:                    Unit
    current_hp:              int
    current_cooldown:        int                        # initialized to max_cooldown - pre_charge
    combat_stats:            StatBlock | None = None
    defensive_stat:          Literal["defense", "res"] | None = None
    damage_mitigated_bucket: int = 0                   # cumulated mitigated damage (for reflex, etc.)
    bonus_count:             int = 0                   # number of active bonuses
    penalty_count:           int = 0                   # number of active penalties
    special_use_count:       int = 0                   # times the Special was used this combat
    strike_count:            int = 0                   # times the unit has struck this combat
    has_entered_combat:      bool = False              # whether the unit already entered combat this turn
    is_initiator:            bool = False              # whether this unit initiated combat
    triggers_brave:          bool = False              # set during strike-sequence determination; read by triggers_brave condition
    spaces_moved:            int = 0                   # spaces moved before combat (clash conditions)
    effects_AoE:             list[Effect] = field(default_factory=list)
    effects_start_of_combat: list[Effect] = field(default_factory=list)
    effects_strike_sequence: list[Effect] = field(default_factory=list)
    effects_pre_combat:      list[Effect] = field(default_factory=list)
    effects_on_strike:       list[Effect] = field(default_factory=list)
    effects_after_combat:    list[Effect] = field(default_factory=list)
    effects_start_of_turn: list[Effect] = field(default_factory=list)
    effects_AoE: list[Effect] = field(default_factory=list)
    effects_start_of_combat: list[Effect] = field(default_factory=list)
```
`effects_start_of_turn` : for effects that grant visible stats or statuses at the start of the turn, i.e. of type `EffectType.GRANT_VISIBLE_STAT` and `EffectType.GRANT_STATUS`.
`effects_AoE` : for effects related to AoE, for example effects of type `EffectType.TRIGGER_AOE`, `EffectType.HEXBLADE_AOE`, `EffectType.PULSE_AOE`, `EffectType.FLAT_DR_AOE`, etc.

`effects_start_of_combat` : for effects that impact in-combat stats, i.e. of type `EffectType.STAT_BOOST` and `EffectType.STAT_DAUNT`.

`effects_strike_sequence` : for effects used to determine the strike sequence, for example effects of type `EffectType.FLASH`, `EffectType.GFU`, `EffectType.POTENT`, `EffectType.BRAVE`, `EffectType.VANTAGE`, `EffectType.DESPERATION_NEUT`, etc.

`effects_pre_combat` : for pre-combat damage and healing effects, i.e. of type `EffectType.PRE_CBT_DAMAGE`, `EffectType.PRE_CBT_HEAL`.

`effects_on_strike` : for per-strike effects, for example effects of type `EffectType.FLAT_DR_STRIKE`, `EffectType.PERC_DR_STRIKE`, `EffectType.FLAT_DAMAGE_STRIKE`, `EffectType.PULSE_STRIKE`, `EffectType.SCOWL_STRIKE`, `EffectType.HEAL_STRIKE`, `EffectType.OFF_BREATH`, `EffectType.DEF_TEMPO`, etc.

`effects_after_combat` : for post-combat effects, for example effects of type `EffectType.HEAL_POST_CBT`, `EffectType.DAMAGE_POST_CBT`.

---

## Condition System

A condition is a tree made up of two node types:

```python
Phase = Literal["pre_aoe", "start_of_combat", "post_sequence"]

@dataclass
class AtomicCondition:
    type:   str       # "ally_within_spaces", "unit_initiates", "hp_above_pct", "triggers_brave"...
    params: dict      # {"min_allies": 1, "spaces": 3}, {"threshold": 25}, {}...
    phase:  Phase     # deduced from the type at startup via CONDITION_REGISTRY, not stored in JSON
    func:   Callable  # (unit: CombatantState, foe: CombatantState) -> bool

@dataclass
class AnyOf:
    conditions: list[Condition]

@dataclass
class AllOf:
    conditions: list[Condition]

Condition = AtomicCondition | AnyOf | AllOf
```

**Phase `pre_aoe`** : evaluated before AoE. Covers conditions based on map context and visible stats: allies or foes within range, visible stats, transformation (beasts), `has_entered_combat`, active bonuses/penalties, Divine Vein or tile effects, initiation, weapon range, number of spaces moved, combat style, foe's movement type or color, Savior, equipped Special.

**Phase `start_of_combat`** : evaluated after `_combat_stat_calculations`. Covers conditions based on HP at the start of combat and on in-combat stats.

**Phase `post_sequence`** : evaluated after `_determine_strike_sequence`. Covers conditions that depend on the result of the strike sequence, for example whether the foe triggers the "attacks twice" effect.

For an `Effect` `example`, `example.conditions` is a `list[Condition]`. The list is an implicit **AND** at the root level.

**JSON encoding of conditions:**
- A flat array is an implicit AND
- `{ "any_of": [...] }` for OR
- `{ "all_of": [...] }` for an explicit AND (useful nested inside an `any_of`)
- Nodes are recursive and can be nested

**Logical encoding example:**
- `(A or B or C) and (D or E) and G` → `[AnyOf([A, B, C]), AnyOf([D, E]), G]`

**Compiled at startup:** for each `AtomicCondition`, the condition type is used to:
1. Deduce the `phase` via `CONDITION_REGISTRY[type][0]`
2. Retrieve the evaluation function via `CONDITION_REGISTRY[type][1]` and call it with `params` to produce `func`

**Evaluator:** at each phase, for each effect, the evaluator walks through `example.conditions`:
- `AtomicCondition` of the current phase → evaluates `func`:
  - `True`: removes this node from the list
  - `False`: removes the entire effect from the phase list
- `AtomicCondition` of another phase → ignored
- `AnyOf` → applies the same logic recursively on children belonging to the current phase
- Empty list → the effect is active
- `AllOf` → like `AnyOf`, but all current-phase children must pass; recurses on children belonging to the current phase


**Concrete condition examples:**

*Momentum 4:*
>"If unit or foe initiates combat after moving to a different space"

```python
condition = [
    AnyOf([
        AtomicCondition("spaces_moved", {}, "pre_aoe", ...)
    ])
]
```
```json
[
    { "any_of": [
        { "type": "spaces_moved", "params": {} }
    ]}
]
```

*Pair Up 4:*
>"If unit is within 3 spaces of an ally [...] and also, if foe triggers the 'attacks twice' effect"
```python
condition = [
    AtomicCondition("ally_within_spaces", {"min_allies": 1, "spaces": 3}, "pre_aoe",    ...),
    AtomicCondition("triggers_brave",     {"target": "foe"},                             "post_sequence", ...)
]
```
```json
[
    { "type": "ally_within_spaces", "params": { "min_allies": 1, "spaces": 3 } },
    { "type": "triggers_brave",     "params": {"target": "foe"} }
]
```

*Atk/Spd Aria:*
>"If unit initiates combat or is within 3 spaces of an ally"
```python
condition = [
    AnyOf([
        AtomicCondition("unit_initiates",     {},                             "pre_aoe", ...),
        AtomicCondition("ally_within_spaces", {"min_allies": 1, "spaces": 3}, "pre_aoe", ...)
    ])
]
```
```json
[
    { "any_of": [
        { "type": "unit_initiates",     "params": {} },
        { "type": "ally_within_spaces", "params": { "min_allies": 1, "spaces": 3 } }
    ]}
]
```

*Deep-Blue Bow:*
>"At start of combat, if unit's HP ≥ 25%, [...] and also, if foe uses sword/lance/axe/dragon/beast and unit's Spd ≥ foe's Spd+5"
```python
condition = [
    AtomicCondition("hp_above_pct",         {"unit": "self", "threshold": 25},                        "start_of_combat", ...),
    AtomicCondition("foe_weapon_type",      {"types": ["SWORD", "LANCE", "AXE", "DRAGON", "BEAST"]},  "pre_aoe",         ...),
    AtomicCondition("cbt_stat_check",       {"stat": "spd", "unit": "self", "margin": -5},                           "start_of_combat", ...)
]
```
```json
[
    { "type": "hp_above_pct",     "params": { "unit": "self", "threshold": 25 } },
    { "type": "foe_weapon_type",  "params": { "types": ["SWORD", "LANCE", "AXE", "DRAGON", "BEAST"] } },
    { "type": "cbt_stat_check",   "params": { "stat": "spd", "unit": "self", "margin": -5 } }
]
```

*Eldhrìmnir:*
>"At start of combat, if unit's Res > foe's Res"
```python
condition = [
    AtomicCondition("visible_stat_check", {"stat": "res", "unit": "self", "margin": 0}, "start_of_combat", ...)
]
```
```json
[
    { "type": "visible_stat_check", "params": { "stat": "res", "unit": "self", "margin": 0 } }
]
```

**`CONDITION_REGISTRY`** : `dict[str, tuple[Phase, Callable[[dict], Callable]]]` defined in `conditions.py`. Maps each condition type to its evaluation phase and its evaluator factory. When an `AtomicCondition` is instantiated, `CONDITION_REGISTRY[type][0]` provides the phase and `CONDITION_REGISTRY[type][1](params)` produces `func`. The benefit is that `params` is captured in the closure once at initialization, rather than being passed on every evaluation.

Example for the two condition types from "Pair Up 4":

```python
def _evaluate_ally_within_spaces(params: dict) -> Callable:
    min_allies = params["min_allies"]
    spaces     = params["spaces"]
    def evaluate(unit: CombatantState, foe: CombatantState) -> bool:
        ...
    return evaluate

def _evaluate_triggers_brave(params: dict) -> Callable:
    def evaluate(unit: CombatantState, foe: CombatantState) -> bool:
        ...
    return evaluate

CONDITION_REGISTRY: dict[str, tuple[Phase, Callable[[dict], Callable]]] = {
    "ally_within_spaces": ("pre_aoe",       _evaluate_ally_within_spaces),
    "triggers_brave":     ("post_sequence", _evaluate_triggers_brave),
    ...
}
```

Initializing an `AtomicCondition` from a JSON dict looks like:

```python
def _build_atomic_condition(data: dict) -> AtomicCondition:
    type  = data["type"]
    params = data.get("params", {})
    return AtomicCondition(
        type   = type,
        params = params,
        phase  = CONDITION_REGISTRY[type][0],
        func   = CONDITION_REGISTRY[type][1](params)
    )
```

---

## JSON Parsing

At startup, three JSON files are parsed to build the in-memory databases.

**Skills**: each entry in the JSON is transformed into a `Skill` object. The `might`, `range`, and `slaying` fields are read from `visible`. The `grants` become a `StatBlock` (`visible_stats`). Restrictions (`allowed_movement_types`, `allowed_weapon_types`, `is_prf`, etc.) are read directly. The `effects` list is kept as-is as a `list[dict]` — it is not compiled at this stage.

**Statuses**: each entry is transformed into a `Status` object and routed into `BONUS_DATABASE` or `PENALTY_DATABASE` according to its `type` field. The `effects` list is likewise kept as a `list[dict]`.

**Units**: raw data is stored in `UNIT_DATABASE` without instantiation — it is used solely to pre-populate a `Unit`'s fields when the user selects a hero.

**Conditions**: conditions are not compiled when `Skill` and `Status` objects are loaded. They are compiled into `AtomicCondition` objects (with `phase` and `func`) when `Effect` instances are created at the start of each simulation. At that point, `CONDITION_REGISTRY` provides both the phase and the function to produce `func`.

---

## User Flow

1. **Startup**: JSON files are read. `SKILL_DATABASE`, `BONUS_DATABASE`, `PENALTY_DATABASE`, and `UNIT_DATABASE` are built in memory. `BONUS_DATABASE` and `PENALTY_DATABASE` are fed from a single status JSON.
2. **Team building**: the user selects a unit → a `Unit` instance is created from `UNIT_DATABASE` data. The user assigns skills → `Unit` slots receive references to `Skill` objects from `SKILL_DATABASE`. The user adds statuses → `unit.active_statuses` receives references to `Status` objects from `BONUS_DATABASE` or `PENALTY_DATABASE`.
3. **Simulation launch**: the `Skill` and `Status` objects of both units are read to instantiate `Effect` objects (with condition compilation) and distribute them into the 6 lists of each `CombatantState`.

---
## Damage Calculation Pipeline

1. **Base damage** — `max(0, trunc(Atk × effectiveness × WTA) − defensive_stat)`.
   Effectiveness (×1.5, unless `NEUT_EFFECTIVE`) and the weapon-triangle
   multiplier (`_get_wta_multiplier`, incl. Triangle Adept / Cancel Affinity)
   apply to Atk here.
2. **Fixed / true damage** — `FLAT_DAMAGE_STRIKE` effects added on
   (Change of Fate, Treachery, etc.).
3. **Offensive Special damage** — special-trigger damage boosts.
4. **StaffMod** — staff users deal ×0.5 unless Wrathful.
5. **Percent damage reduction** — all percent DR is expressed as a single
   `PERC_DR_STRIKE` effect type with a `piercable: bool` param:
   - `piercable: true` (default; non-Special sources): reduced by `DR_PIERCE`
     (`pierce_mult`) before stacking, and (⚠ future) halvable by "reduce foe's
     DR%" effects. Multiple pierceable sources stack multiplicatively into
     one product.
   - `piercable: false` (Special-grade, Pavise/Aegis): NOT reduced by
     `DR_PIERCE`, NOT halvable. Kept in its own product, immune to piercing.
   The two products combine multiplicatively (`1 − (1−perc)(1−unpierceable)`)
   and never reach 100% from percentages alone (e.g. Dodge 40% + Archrival
   40% → 64% total, not 80%).
6. **Flat damage reduction** — `FLAT_DR_STRIKE` subtracted, floored at 0.
7. **Damage floor** — `DR_FLOOR` caps the damage at a maximum (Collapsed Star
   "reduce to 1"): if `final_damage > floor`, set to `floor`. Lowest floor wins.
8. **Survival effects** — Miracle / survive-at-1-HP.

Percent DR (step 5) is applied AFTER fixed/true damage (step 2) and offensive
Specials (step 3), matching the wiki. Flat DR (step 6) and the floor (step 7)
come after percent DR.

## Simulation Timeline

*Note: Start-of-Turn is ignored for now.*
1. Call `_phase_start_of_turn`: processes `effects_start_of_turn`, granting visible stats and statuses (two passes: unconditional, then conditional). Then `_compute_counts` tallies `bonus_count` / `penalty_count` from the resulting buffs, debuffs, and statuses.

2. Initialize `self.combatant_states`: parse both units' skills and statuses to create `Effect` objects and distribute them into the 6 lists. Load the map context.

3. Call `_evaluate_conditions("pre_aoe")`: evaluates phase `pre_aoe` conditions (visible stats, initiation, etc.).

4. Call `_phase_AoE`: processes `effects_AoE`.

5. Call `_combat_stat_calculations`: processes `effects_start_of_combat` and computes the in-combat stats for both units.

6. Call `_evaluate_conditions("start_of_combat")`: evaluates phase `start_of_combat` conditions (HP% and in-combat stats).

7. Call `_determine_strike_sequence`: processes `effects_strike_sequence` to determine the strike sequence.

8. Call `_evaluate_conditions("post_sequence")`: evaluates phase `post_sequence` conditions (e.g. the foe triggers the "attacks twice" effect).

9. Call `_phase_pre_combat`: processes `effects_pre_combat` (Flared Sparrow, BoL, etc.).

10. Loop over the strike sequence consulting `effects_on_strike`.

11. Call `_phase_after_combat`: processes `effects_after_combat`.

---

## Appendix — Reference Tables

### A - Effect Type Reference

---
#### `effects_start_of_turn`

Processed by `_phase_start_of_turn` before combat begins. These grant visible stats and statuses to a unit (or foe) at the start of the turn. Grants are written per-combat onto the `CombatantState` (`granted_visible_buffs` / `granted_visible_debuffs` / `granted_statuses`), never mutating the `Unit`, so repeated simulations stay isolated. Evaluated in two passes: unconditional grants first, then conditional grants (e.g. Ploy) so their conditions see the results of the earlier grants.

| Effect | Description | `params` |
|---|---|---|
| `GRANT_VISIBLE_STAT` | Grants visible (stat-screen) stat changes to the target at start of turn. Positive values become visible buffs, negative values become visible debuffs. Feeds `CombatantState.visible_stat()` and the bonus/penalty counts. | `{ stats: { atk: int, spd: int, defense: int, res: int } }` (only the stats being changed need be listed) |
| `GRANT_STATUS` | Grants a named status to the target at start of turn, looked up by name in `BONUS_DATABASE` / `PENALTY_DATABASE` and appended to `granted_statuses`. Skipped if the target already has a status of that name (in `active_statuses` or `granted_statuses`), so non-stacking statuses aren't duplicated. | `{ status: str }` (the status name, must exist in a database) |

#### `effects_AoE`

| Effect | Description | `params` |
|---|---|---|
| `TRIGGER_AOE` | Before combat foe takes damage | `{ coefficient: float }` |
| `FLAT_DAMAGE_AOE` | Unit deals +X damage when dealing damage with a Special triggered before combat | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |
| `FLAT_DR_AOE` | Reduce damage by X when foe deals damage with a Special triggered before combat | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |
| `HEXBLADE_AOE` | Calculates damage using the lower of foe's Def or Res when dealing damage with a Special triggered before combat | `{}` |
| `PULSE_AOE` | Grants Special cooldown count -X to unit before Special triggers before combat | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |

#### `effects_start_of_combat`

| Effect | Description | `params` |
|---|---|---|
| `STAT_BOOST` | Grants +X to specific stats to unit | `{ stats: list[str] } + { formula: str, multiplier: float, flat: int, min: int, max: int }` |
| `STAT_DAUNT` | Inflicts -X to specific stats to unit | `{ stats: list[str] } + { formula: str, multiplier: float, flat: int, min: int, max: int }` |
| `BONUS_NEUT` | Neutralizes bonuses to specific stats | `{}` |
| `PENALTY_NEUT` | Neutralizes penalties to specific stats | `{}` |

#### `effects_strike_sequence`

| Effect | Description | `params` |
|---|---|---|
| `FU_DENY` | Foe cannot make follow-up attack | `{}` |
| `GFU` | Unit makes a guaranteed follow-up | `{}` |
| `OFF_NFU` | Neutralizes effects that prevent unit's follow-up attacks | `{}` |
| `DEF_NFU` | Neutralizes effects that guarantee foe's follow-up attacks | `{}` |
| `BRAVE` | Unit attacks twice | `{}` |
| `POTENT` | Triggers an additional follow-up attack immediately after unit's standard follow-up attack | `{}` |
| `VANTAGE` | Unit can counterattack before foe's first attack | `{}` |
| `VANTAGE_NEUT` | Neutralizes that allow unit to counterattack before foe's first attack | `{}` |
| `DESPERATION` | Unit can make a follow-up attack before foe can counterattack / Unit can make a follow-up attack before foe's next attack | `{}` |
| `DESPERATION_NEUT` | Neutralizes effects that allow unit to make a follow-up attack before foe's next attack  | `{}` |
| `FLASH` | Unit cannot counterattack | `{}` |
| `FLASH_NEUT` | Neutralizes effects that prevent unit's counterattacks | `{}` |
| `OFF_FROZEN` | Decreases Spd difference necessary for unit to make a follow-up attack by X | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |
| `DEF_FROZEN` | Increases Spd difference necessary for unit to make a follow-up attack by X | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |

#### `effects_pre_combat`

| Effect | Description | `params` |
|---|---|---|
| `PRE_CBT_DAMAGE` | Deals damage to unit as combat begins | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |
| `PRE_CBT_HEAL` | Restores HP to unit as combat begins | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |

#### `effects_on_strike`

| Effect | Description | `params` |
|---|---|---|
| `DR_PIERCE` | Reduces the percentage of unit's non-Special "reduces damage by X%" | `{ value: int, strike }` |
| `HEXBLADE_STRIKE` | Calculates damage using the lower of foe's Def or Res | `{}` |
| `EFFECTIVE` | Effective against specific unit type | `{ movement_types: list[str], weapon_types: list[str] }` |
| `NEUT_EFFECTIVE` | Neutralizes 'effective against specific unit type' | `{ movement_types: list[str], weapon_types: list[str] }` |
| `SPECIAL_TRIGGER_NEUT` | Unit cannot trigger Specials | `{}` |
| `FLAT_DR_STRIKE` | Reduce damage from specific foe's attacks by X during combat | `{ formula: str, multiplier: float, flat: int, min: int, max: int, strike: str }` |
| `PERC_DR_STRIKE` | Reduce damage from specific foe's attacks during combat by X%. `piercable` (default `true`) sources stack in one product and are reduced by `DR_PIERCE`; `piercable: false` (Special-grade, e.g. Pavise/Aegis) sources stack in a separate, pierce-immune product | `{ formula: str, multiplier: float, flat: int, min: int, max: int, strike: str, piercable: bool }` |
| `FLAT_DAMAGE_STRIKE` | Unit deals +X damage | `{ formula: str, multiplier: float, flat: int, min: int, max: int, strike: str }` |
| `PULSE_STRIKE` | Grants Special count -X to unit before specific strikes | `{ formula: str, multiplier: float, flat: int, min: int, max: int, strike: str, cap_cd_start_of_cbt: bool }` |
| `SCOWL_STRIKE` | Inflicts Special cooldown count + X on unit before unit's specific attacks | `{ formula: str, multiplier: float, flat: int, min: int, max: int, strike: str }` |
| `HEAL_STRIKE` | When unit deals damage to foe , restores X HP to unit| `{ formula: str, multiplier: float, flat: int, min: int, max: int, strike: str }` |
| `OFF_BREATH` | Grants Special cooldown charge +1 per unit's attack | `{}` |
| `DEF_BREATH` | Grants Special cooldown charge +1 per foe's attack | `{}` |
| `BREATH_NEUT` | Neutralizes effects that grant "Special cooldown charge +X" on unit | `{}` |
| `OFF_GUARD` | Inflicts Special cooldown charge -1 per foe's attack | `{}` |
| `DEF_GUARD` | Inflicts Special cooldown charge -1 per unit's attack | `{}` |
| `GUARD_NEUT` | Neutralizes effects that inflict "Special cooldown charge -X" on unit | `{}` |
| `DR_FLOOR` | Reduces damage from specific unit's attack to a maximum of X during combat (X resolved via the formula block; "floor to 1" is `flat: 1`) | `{ formula: str, multiplier: float, flat: int, min: int, max: int, strike: str }` |

| `DEEP_WOUNDS_IN_CBT` | Unit cannot be healed during combat (pre-combat and per-strike heals). Stored in the **afflicted** unit's list and checked against that unit's own heals. So for a skill like fatal smoke 4, it would check the `target: "foe"` (routed into the foe's list), while a carried status uses `target: "self"`. | `{}` |
| `NEUT_DEEP_WOUNDS_IN_CBT` | Neutralizes \[Deep Wounds] for in-combat healing. Self-protective: lives in the protected unit's own list (`target: "self"`), checked alongside any Deep Wounds afflicting that same unit. | `{}` |
| `REDUCE_DEEP_WOUNDS_IN_CBT` | Reduces \[Deep Wounds] for in-combat healing — lets a % of healing through. Multiple sources stack multiplicatively and the surviving heal rounds UP | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |
| `TRIANGLE_ADEPT` | Amplifies an existing Weapon Triangle advantage (on either combatant) to a larger magnitude. Never creates advantage where none exists | `{ flat: int }` (the advantage %, e.g. 40) |
| `CANCEL_AFFINITY` | Neutralizes Triangle Adept amplification (on either side), reverting to the base ±20% Weapon Triangle | `{}` |

#### `effects_after_combat`

| Effect | Description | `params` |
|---|---|---|
| `HEAL_POST_CBT` | Restores X HP to unit after combat | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |
| `DAMAGE_POST_CBT` | After combat, deals X damage to unit | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |
| `DEEP_WOUNDS_POST_CBT` | Unit cannot be healed after combat | `{}` |
| `NEUT_DEEP_WOUNDS_POST_CBT` | Neutralizes \[Deep Wounds] for post-combat healing | `{}` |
| `REDUCE_DEEP_WOUNDS_POST_CBT` | Reduces \[Deep Wounds] for post-combat healing — lets a % through, stacks multiplicatively, rounds UP | `{ formula: str, multiplier: float, flat: int, min: int, max: int }` |
> **Deep Wounds is split by phase.** In-combat Deep Wounds (`*_IN_CBT`) lives in `effects_on_strike` and gates both pre-combat and per-strike healing; post-combat Deep Wounds (`*_POST_CBT`) lives in `effects_after_combat`. The block is checked per-phase by `_apply_healing(role, amount, phase)`, which selects the matching effect family from the matching list. Reduce effects let a fraction of healing through, stack multiplicatively across sources, and round the surviving heal up.

---

### B - `strike` Value Reference

Used in the `params` of `effects_on_strike` effects to specify which strikes the effect applies to.

| Value | Applies |
|---|---|
| `every_strike` | Every strike of the sequence |
| `first_strike` | First attack, excluding the brave second hit |
| `first_attack` | First attack, including the brave second hit |
| `follow_up` | Follow-up attack, including the brave second hit |
| `first_follow_up` | First follow-up attack, excluding the brave second hit |
| `on_unit_special` | When unit's Special triggers |
| `on_foe_special` | When foe's Special triggers |

---

### C - `formula` Value Reference

Formula names resolve to raw game quantities; skill-specific offsets and caps live in the params (`flat` for offsets, `min`/`max` for clamps), not baked into the formula. For example, the Liberate "+4, max 8" is `"formula": "bonus_count", "multiplier": 1, "flat": 4, "max": 8`, and Dodge's "Spd diff ×4, max 40%" is `"formula": "phantom_spd_diff", "multiplier": 4, "min": 0, "max": 40`.
.

| Value | Resolves to | Extra params |
|---|---|---|
| `""` (empty) | `0` — only the `flat` component applies | — |
| `bonus_count` | Unit's active bonus count | — |
| `penalty_count` | Unit's active penalty count | — |
| `all_bonus_penalty_both` | Sum of bonus + penalty counts on **both** unit and foe (Empathy) | — |
| `spaces_moved` | Spaces the unit moved before combat (Incited / Truly Incited) | — |
| `sum_visible_buffs` | Sum of unit's visible stat bonuses, each floored at 0 (Treachery) | — |
| `sum_foe_visible_debuffs` | Sum of foe's visible stat penalties, each floored at 0 (Dominance) | — |
| `mitigated_bucket` | Unit's accumulated mitigated-damage total (Reflex) | — |
| `unit_max_hp` | Unit's max HP (percent heals: pair with `multiplier`) | — |
| `phantom_spd_diff` | `unit_spd - foe_spd`, in-combat, **including Phantom Spd**, floored at 0 (Dodge: pair with `multiplier`/`max` for the cap). Distinct from the plain `spd_diff` locals used by the follow-up check and `potent_spd_check`, which deliberately exclude Phantom. | — |
| `foe_penalty_count` | Foe's active penalty count (Creation Pulse: pair with `max` for the cap) | — |
| `unit_cbt_atk` | Unit's in-combat Atk | — |
| `unit_cbt_spd` | Unit's in-combat Spd | — |
| `unit_cbt_def` | Unit's in-combat Def | — |
| `unit_cbt_res` | Unit's in-combat Res | — |
| `max_cooldown` | Unit's max Special cooldown count value | — |

---

### D - Condition Type Reference

| Condition | Phase | `params` |
|---|---|---|
| `unit_initiates` | `pre_aoe` | `{}` |
| `foe_initiates` | `pre_aoe` | `{}` |
| `spaces_moved` | `pre_aoe` | `{ "target": "self"\|"foe"\|"either"\|"initiator", "min_spaces": int }` |
| `ally_within_spaces` | `pre_aoe` | `{ "min_allies": int, "spaces": int }` |
| `ally_within_spaces123` | `pre_aoe` | `{ "check": "1_space"\|"2_spaces"\|"3_spaces"\|"3_rows_cols", "min_allies": int, "target": "self"\|"foe" }` |
### NOTE: CHECK WHICH ALLY COND METHOD WE WANT TO USE 
| `foe_weapon_type` | `pre_aoe` | `{ "types": list[str] }` |
| `bonus_penalty_total` | `pre_aoe` | `{ "min_count": int, "include_foe": bool }` |
| `is_engaged` | `pre_aoe` | `{}` |
| `first_combat_of_turn` | `pre_aoe` | `{ "target": "self"\|"foe" }` |
| `hp_above_pct` | `start_of_combat` | `{ "unit": "self"\|"foe", "threshold": int }` |
| `hp_below_pct` | `start_of_combat` | `{ "unit": "self"\|"foe", "threshold": int }` — true when HP% is strictly below threshold (exact complement of `hp_above_pct`) |
| `triggers_brave` | `post_sequence` | `{ "target": "self"\|"foe" }` |
| `cbt_stat_check` | `start_of_combat` | `{ "stat": str, "unit": "self"\|"foe", "margin": int, "comparison": "greater_or_equal"\|"lesser_than" }` | *`cbt_stat_check`'s `comparison` is optional and defaults to `greater_or_equal` (`unit_stat >= foe_stat + margin`). `lesser_than` evaluates `unit_stat < foe_stat + margin`. The two are exact complements at the same `margin`, so a pair of effects with opposite comparisons partitions every case (e.g. Breath of Life 4's 40%/20% heal split on Def).*
| `visible_stat_check` | `start_of_turn` | `{ "stat": str, "margin": int, "comparison": "greater_or_equal"\|"lesser_than" }` | Same semantics as `cbt_stat_check` but compares visible stats via `CombatantState.visible_stat()` (Ploy, Eldhrímnir). The `start_of_turn` phase is NOT part of the three-phase `_evaluate_conditions` system — it's evaluated eagerly by `_start_of_turn_conditions_pass`, which calls `cond.func` directly, so a conditional grant sees unconditional grants applied earlier in the same pass. |



