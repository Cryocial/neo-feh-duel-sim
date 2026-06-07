import json

STATUS_EFFECT_DATABASE = {} 

def initialize_status_database():
    """Runs once when the server starts to build the database."""
    
    with open('statuses.json', 'r') as file:
        raw_json_data = json.load(file)
        
    for status_name, status_info in raw_json_data.items():
        
        combat_stats = StatBlock(**status_info.get("combat_stats", {}))
        
        utilities = UtilityBlock()
        utility_data = status_info.get("utilities", {})
        
        if "logic_tag" in utility_data:
            tag = utility_data["logic_tag"]
            if tag in LOGIC_REGISTRY:
                logic_functions = LOGIC_REGISTRY[tag]
                utilities.truedr_logic = logic_functions.get("truedr_logic")
                utilities.truedmg_logic = logic_functions.get("truedmg_logic")
                # Add any other logic slots here...
                
        STATUS_EFFECT_DATABASE[status_name] = {
            "combat_stats": combat_stats,
            "utilities": utilities
        }

initialize_status_database()