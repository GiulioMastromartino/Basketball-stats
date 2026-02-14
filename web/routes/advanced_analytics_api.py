    # Calculate usage rate
    from core.utils import parse_minutes
    
    # Handle minutes parsing safely
    if isinstance(player_result.minutes, str):
        minutes_str_list = (player_result.minutes or "").split(",")
        minutes = sum(parse_minutes(m) for m in minutes_str_list)
    elif isinstance(player_result.minutes, (int, float)):
        # If already aggregated as number (e.g. from sum() in query)
        minutes = float(player_result.minutes)
    else:
        # Fallback estimation
        minutes = player_result.games * 25
    
    usage = AdvancedPlayerStats.calculate_true_usage_rate(
