def sync_turn_limit_for_kingdom(kingdom):
    if hasattr(kingdom, "turn_limit"):
        kingdom.turn_limit.sync_with_premium_status()