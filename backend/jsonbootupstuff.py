import json

STATUS_EFFECT_DATABASE = {} 

def initialize_status_database():
    """Runs once when the server starts to build the database."""
    
   with open('visualbonuses.json', 'r') as file:
        raw_json_data = json.load(file)
        
    for status_name, status_info in raw_json_data.items():
        combat_stats = StatBlock(**status_info.get("combat_stats", {}))
        utilities = UtilityBlock()
        utility_data = status_info.get("utilities", {})
        
        utilities.keywords = utility_data.get("keywords", [])
        utilities.cooldown_modifiers = utility_data.get("cooldown_modifiers", {})
        
        if "logic_tag" in utility_data:
            tag = utility_data["logic_tag"]
            if tag in LOGIC_REGISTRY:
                logic_functions = LOGIC_REGISTRY[tag]
                utilities.truedr_logic = logic_functions.get("truedr_logic")
                utilities.truedmg_logic = logic_functions.get("truedmg_logic")
                utilities.dynamic_stats_logic = logic_functions.get("dynamic_stats_logic") 
initialize_status_database()