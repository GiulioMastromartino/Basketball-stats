class DataValidator:
    @staticmethod
    def validate_player_stats(stats):
        required = ['name', 'points', 'minutes']
        for field in required:
            if field not in stats:
                raise ValueError(f"Missing field: {field}")
        return stats
