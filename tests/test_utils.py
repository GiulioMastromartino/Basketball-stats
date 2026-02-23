"""
Unit tests for core/utils.py calculation functions.

Tests all statistical calculation functions with edge cases.
"""

import pytest
from core.utils import (
    safe_divide,
    safe_percentage,
    parse_minutes,
    calculate_possessions,
    calculate_ortg,
    calculate_ppp,
    calculate_ts_percent,
    calculate_efg_percent,
    calculate_usg_percent,
    calculate_ast_tov_ratio,
    calculate_oreb_percent,
    calculate_game_score,
    calculate_two_point_stats,
    calculate_efficiency,
    calculate_fta_rate,
    normalize_per_100_possessions,
    calculate_per_100_minutes,
    normalize_date_to_display,
    get_player_stats_averages,
)


# =============================================================================
# safe_divide Tests
# =============================================================================

class TestSafeDivide:
    """Tests for safe_divide function."""
    
    @pytest.mark.unit
    def test_normal_division(self):
        """Test normal division cases."""
        assert safe_divide(10, 2) == 5.0
        assert safe_divide(100, 4) == 25.0
        assert safe_divide(7, 3) == pytest.approx(2.333333, rel=1e-5)
    
    @pytest.mark.unit
    def test_division_by_zero(self):
        """Test division by zero returns default."""
        assert safe_divide(10, 0) == 0.0
        assert safe_divide(100, 0) == 0.0
    
    @pytest.mark.unit
    def test_division_by_zero_custom_default(self):
        """Test division by zero with custom default."""
        assert safe_divide(10, 0, default=-1) == -1
        assert safe_divide(100, 0, default='N/A') == 'N/A'
    
    @pytest.mark.unit
    def test_negative_numbers(self):
        """Test division with negative numbers."""
        assert safe_divide(-10, 2) == -5.0
        assert safe_divide(10, -2) == -5.0
        assert safe_divide(-10, -2) == 5.0
    
    @pytest.mark.unit
    def test_zero_numerator(self):
        """Test zero numerator."""
        assert safe_divide(0, 5) == 0.0
        assert safe_divide(0, 100) == 0.0
    
    @pytest.mark.unit
    def test_float_inputs(self):
        """Test with float inputs."""
        assert safe_divide(10.5, 2.0) == 5.25
        assert safe_divide(0.5, 0.25) == 2.0


# =============================================================================
# safe_percentage Tests
# =============================================================================

class TestSafePercentage:
    """Tests for safe_percentage function."""
    
    @pytest.mark.unit
    def test_normal_percentage(self):
        """Test normal percentage calculation."""
        assert safe_percentage(50, 100) == 50.0
        assert safe_percentage(25, 50) == 50.0
        assert safe_percentage(1, 4) == 25.0
    
    @pytest.mark.unit
    def test_percentage_with_decimals(self):
        """Test percentage with decimal precision."""
        assert safe_percentage(1, 3, decimals=2) == pytest.approx(33.33, rel=1e-2)
        assert safe_percentage(2, 3, decimals=3) == pytest.approx(66.667, rel=1e-3)
    
    @pytest.mark.unit
    def test_percentage_zero_denominator(self):
        """Test percentage with zero denominator."""
        assert safe_percentage(50, 0) == 0.0
    
    @pytest.mark.unit
    def test_percentage_over_100(self):
        """Test percentage can exceed 100."""
        assert safe_percentage(150, 100) == 150.0
    
    @pytest.mark.unit
    def test_percentage_zero_numerator(self):
        """Test percentage with zero numerator."""
        assert safe_percentage(0, 100) == 0.0


# =============================================================================
# parse_minutes Tests
# =============================================================================

class TestParseMinutes:
    """Tests for parse_minutes function."""
    
    @pytest.mark.unit
    def test_valid_minutes_seconds(self):
        """Test parsing valid MM:SS format."""
        assert parse_minutes('12:30') == 12.5
        assert parse_minutes('24:00') == 24.0
        assert parse_minutes('0:30') == 0.5
        assert parse_minutes('5:45') == 5.75
    
    @pytest.mark.unit
    def test_zero_minutes(self):
        """Test parsing zero values."""
        assert parse_minutes('00:00') == 0.0
        assert parse_minutes('0') == 0.0
        assert parse_minutes('0:00') == 0.0
    
    @pytest.mark.unit
    def test_none_value(self):
        """Test parsing None."""
        assert parse_minutes(None) == 0.0
    
    @pytest.mark.unit
    def test_empty_string(self):
        """Test parsing empty string."""
        assert parse_minutes('') == 0.0
    
    @pytest.mark.unit
    def test_invalid_format(self):
        """Test parsing invalid format returns 0."""
        assert parse_minutes('invalid') == 0.0
        assert parse_minutes('abc:def') == 0.0
    
    @pytest.mark.unit
    def test_invalid_seconds_over_59(self):
        """Test parsing with invalid seconds (>59)."""
        assert parse_minutes('10:60') == 0.0
        assert parse_minutes('10:99') == 0.0
    
    @pytest.mark.unit
    def test_decimal_string(self):
        """Test parsing decimal string."""
        assert parse_minutes('15.5') == 15.5
        assert parse_minutes('20.25') == 20.25


# =============================================================================
# calculate_possessions Tests
# =============================================================================

class TestCalculatePossessions:
    """Tests for calculate_possessions function.
    
    Formula: FGA + 0.44*FTA - ORB + TOV
    """
    
    @pytest.mark.unit
    def test_standard_possessions(self):
        """Test standard possession calculation."""
        result = calculate_possessions(70, 20, 10, 15)
        assert result == pytest.approx(83.8, rel=1e-5)
    
    @pytest.mark.unit
    def test_possessions_no_ft(self):
        """Test possessions with no free throws."""
        result = calculate_possessions(50, 0, 5, 10)
        assert result == 55.0
    
    @pytest.mark.unit
    def test_possessions_all_zeros(self):
        """Test possessions with all zeros."""
        result = calculate_possessions(0, 0, 0, 0)
        assert result == 0.0
    
    @pytest.mark.unit
    def test_possessions_high_ft(self):
        """Test possessions with high free throw rate."""
        result = calculate_possessions(40, 40, 8, 12)
        assert result == pytest.approx(61.6, rel=1e-5)


# =============================================================================
# calculate_ortg Tests
# =============================================================================

class TestCalculateOrtg:
    """Tests for calculate_ortg (Offensive Rating) function."""
    
    @pytest.mark.unit
    def test_standard_ortg(self):
        """Test standard offensive rating."""
        result = calculate_ortg(100, 80)
        assert result == 125.0
    
    @pytest.mark.unit
    def test_ortg_zero_possessions(self):
        """Test ORtg with zero possessions."""
        result = calculate_ortg(100, 0)
        assert result == 0.0
    
    @pytest.mark.unit
    def test_ortg_zero_points(self):
        """Test ORtg with zero points."""
        result = calculate_ortg(0, 80)
        assert result == 0.0
    
    @pytest.mark.unit
    def test_ortg_high_efficiency(self):
        """Test high efficiency ORtg."""
        result = calculate_ortg(120, 75)
        assert result == pytest.approx(160.0, rel=1e-5)
    
    @pytest.mark.unit
    def test_ortg_low_efficiency(self):
        """Test low efficiency ORtg."""
        result = calculate_ortg(60, 80)
        assert result == 75.0


# =============================================================================
# calculate_ppp Tests
# =============================================================================

class TestCalculatePpp:
    """Tests for calculate_ppp (Points Per Possession) function."""
    
    @pytest.mark.unit
    def test_standard_ppp(self):
        """Test standard PPP calculation."""
        result = calculate_ppp(80, 70)
        assert result == pytest.approx(1.143, rel=1e-2)
    
    @pytest.mark.unit
    def test_ppp_zero_possessions(self):
        """Test PPP with zero possessions."""
        result = calculate_ppp(100, 0)
        assert result == 0.0
    
    @pytest.mark.unit
    def test_ppp_excellent(self):
        """Test excellent PPP."""
        result = calculate_ppp(90, 70)
        assert result == pytest.approx(1.286, rel=1e-2)


# =============================================================================
# calculate_ts_percent Tests
# =============================================================================

class TestCalculateTsPercent:
    """Tests for calculate_ts_percent (True Shooting Percentage) function."""
    
    @pytest.mark.unit
    def test_standard_ts(self):
        """Test standard TS%."""
        result = calculate_ts_percent(18, 14, 3)
        assert result == pytest.approx(58.75, rel=1e-1)
    
    @pytest.mark.unit
    def test_ts_zero_attempts(self):
        """Test TS% with zero attempts."""
        result = calculate_ts_percent(0, 0, 0)
        assert result == 0.0
    
    @pytest.mark.unit
    def test_ts_no_ft(self):
        """Test TS% with no free throws."""
        result = calculate_ts_percent(20, 10, 0)
        assert result == 100.0
    
    @pytest.mark.unit
    def test_ts_elite(self):
        """Test elite TS%."""
        result = calculate_ts_percent(25, 15, 4)
        assert result == pytest.approx(74.58, rel=1e-1)


# =============================================================================
# calculate_efg_percent Tests
# =============================================================================

class TestCalculateEfgPercent:
    """Tests for calculate_efg_percent (Effective Field Goal Percentage) function."""
    
    @pytest.mark.unit
    def test_standard_efg(self):
        """Test standard eFG%."""
        result = calculate_efg_percent(7, 2, 14)
        assert result == pytest.approx(57.14, rel=1e-1)
    
    @pytest.mark.unit
    def test_efg_zero_attempts(self):
        """Test eFG% with zero attempts."""
        result = calculate_efg_percent(5, 2, 0)
        assert result == 0.0
    
    @pytest.mark.unit
    def test_efg_no_threes(self):
        """Test eFG% with no three-pointers."""
        result = calculate_efg_percent(7, 0, 14)
        assert result == 50.0
    
    @pytest.mark.unit
    def test_efg_all_threes(self):
        """Test eFG% when all makes are threes."""
        result = calculate_efg_percent(5, 5, 10)
        assert result == 75.0


# =============================================================================
# calculate_usg_percent Tests
# =============================================================================

class TestCalculateUsgPercent:
    """Tests for calculate_usg_percent (Usage Percentage) function."""
    
    @pytest.mark.unit
    def test_standard_usg(self):
        """Test standard usage percentage."""
        result = calculate_usg_percent(20, 100)
        assert result == 20.0
    
    @pytest.mark.unit
    def test_usg_zero_team_possessions(self):
        """Test usage with zero team possessions."""
        result = calculate_usg_percent(20, 0)
        assert result == 0.0
    
    @pytest.mark.unit
    def test_usg_high_usage(self):
        """Test high usage player."""
        result = calculate_usg_percent(35, 100)
        assert result == 35.0
    
    @pytest.mark.unit
    def test_usg_over_100(self):
        """Test usage can exceed 100%."""
        result = calculate_usg_percent(120, 100)
        assert result == 120.0


# =============================================================================
# calculate_ast_tov_ratio Tests
# =============================================================================

class TestCalculateAstTovRatio:
    """Tests for calculate_ast_tov_ratio function."""
    
    @pytest.mark.unit
    def test_standard_ratio(self):
        """Test standard assist-to-turnover ratio."""
        result = calculate_ast_tov_ratio(5, 2)
        assert result == 2.5
    
    @pytest.mark.unit
    def test_ratio_zero_turnovers(self):
        """Test ratio with zero turnovers."""
        result = calculate_ast_tov_ratio(5, 0)
        assert result == 5.0
    
    @pytest.mark.unit
    def test_ratio_zero_assists(self):
        """Test ratio with zero assists."""
        result = calculate_ast_tov_ratio(0, 2)
        assert result == 0.0
    
    @pytest.mark.unit
    def test_ratio_perfect(self):
        """Test perfect ratio."""
        result = calculate_ast_tov_ratio(10, 0)
        assert result == 10.0
    
    @pytest.mark.unit
    def test_ratio_poor(self):
        """Test poor ratio."""
        result = calculate_ast_tov_ratio(2, 5)
        assert result == 0.4


# =============================================================================
# calculate_oreb_percent Tests
# =============================================================================

class TestCalculateOrebPercent:
    """Tests for calculate_oreb_percent function."""
    
    @pytest.mark.unit
    def test_standard_oreb_percent(self):
        """Test standard offensive rebound percentage."""
        result = calculate_oreb_percent(5, 15)
        assert result == pytest.approx(33.33, rel=1e-1)
    
    @pytest.mark.unit
    def test_oreb_percent_zero_total(self):
        """Test OREB% with zero total rebounds."""
        result = calculate_oreb_percent(5, 0)
        assert result == 0.0
    
    @pytest.mark.unit
    def test_oreb_percent_all_offensive(self):
        """Test when all rebounds are offensive."""
        result = calculate_oreb_percent(10, 10)
        assert result == 100.0


# =============================================================================
# calculate_game_score Tests
# =============================================================================

class TestCalculateGameScore:
    """Tests for calculate_game_score function."""
    
    @pytest.mark.unit
    def test_standard_game_score(self):
        """Test standard game score calculation."""
        result = calculate_game_score(
            points=18, fgm=7, fga=14, ftm=2, fta=3,
            oreb=1, dreb=4, stl=2, ast=3, blk=1, pf=3, tov=2
        )
        assert result is not None
        assert result > 0
    
    @pytest.mark.unit
    def test_game_score_excellent(self):
        """Test excellent game score."""
        result = calculate_game_score(
            points=30, fgm=12, fga=20, ftm=4, fta=5,
            oreb=2, dreb=8, stl=3, ast=6, blk=2, pf=2, tov=1
        )
        assert result > 15
    
    @pytest.mark.unit
    def test_game_score_poor(self):
        """Test poor game score."""
        result = calculate_game_score(
            points=2, fgm=1, fga=10, ftm=0, fta=0,
            oreb=0, dreb=1, stl=0, ast=0, blk=0, pf=5, tov=4
        )
        assert result < 5


# =============================================================================
# calculate_two_point_stats Tests
# =============================================================================

class TestCalculateTwoPointStats:
    """Tests for calculate_two_point_stats function."""
    
    @pytest.mark.unit
    def test_standard_two_point(self):
        """Test standard 2-point calculation."""
        result = calculate_two_point_stats(fgm=7, fga=14, tpm=2, tpa=5)
        assert result['two_pt_made'] == 5
        assert result['two_pt_att'] == 9
        assert result['two_pt_pct'] == pytest.approx(55.56, rel=1e-1)
    
    @pytest.mark.unit
    def test_two_point_no_threes(self):
        """Test 2-point stats with no three-pointers."""
        result = calculate_two_point_stats(fgm=7, fga=14, tpm=0, tpa=0)
        assert result['two_pt_made'] == 7
        assert result['two_pt_att'] == 14
        assert result['two_pt_pct'] == 50.0
    
    @pytest.mark.unit
    def test_two_point_all_threes(self):
        """Test when all shots are threes."""
        result = calculate_two_point_stats(fgm=5, fga=10, tpm=5, tpa=10)
        assert result['two_pt_made'] == 0
        assert result['two_pt_att'] == 0
        assert result['two_pt_pct'] == 0.0
    
    @pytest.mark.unit
    def test_two_point_zero_attempts(self):
        """Test with zero attempts."""
        result = calculate_two_point_stats(fgm=0, fga=0, tpm=0, tpa=0)
        assert result['two_pt_made'] == 0
        assert result['two_pt_att'] == 0
        assert result['two_pt_pct'] == 0.0


# =============================================================================
# normalize_date_to_display Tests
# =============================================================================

class TestNormalizeDateToDisplay:
    """Tests for normalize_date_to_display function.
    
    Note: Function expects DD/MM/YYYY or DD-MM-YYYY input and returns DD/MM/YYYY.
    """
    
    @pytest.mark.unit
    def test_dd_mm_yyyy_format(self):
        """Test DD-MM-YYYY format conversion to DD/MM/YYYY."""
        result = normalize_date_to_display('17-02-2024')
        assert result == '17/02/2024'
    
    @pytest.mark.unit
    def test_dd_mm_yyyy_slashes(self):
        """Test DD/MM/YYYY format (already correct)."""
        result = normalize_date_to_display('17/02/2024')
        assert result == '17/02/2024'
    
    @pytest.mark.unit
    def test_empty_string(self):
        """Test empty string."""
        result = normalize_date_to_display('')
        assert result == ''
    
    @pytest.mark.unit
    def test_two_digit_year(self):
        """Test two digit year expansion."""
        result = normalize_date_to_display('17/02/24')
        assert result == '17/02/2024'
    
    @pytest.mark.unit
    def test_single_digit_pad(self):
        """Test single digit day/month padding."""
        result = normalize_date_to_display('7/2/2024')
        assert result == '07/02/2024'


# =============================================================================
# Additional Utils Tests
# =============================================================================

class TestAdditionalUtils:
    """Tests for additional utility functions."""
    
    @pytest.mark.unit
    def test_calculate_efficiency(self):
        """Test efficiency calculation."""
        result = calculate_efficiency(
            points=18, reb=5, ast=3, stl=2, blk=1,
            fgm=7, fga=14, ftm=2, fta=3, tov=2
        )
        assert result is not None
    
    @pytest.mark.unit
    def test_calculate_fta_rate(self):
        """Test FTA rate calculation."""
        result = calculate_fta_rate(10, 50)
        assert result == 20.0
    
    @pytest.mark.unit
    def test_normalize_per_100_possessions(self):
        """Test per 100 possessions normalization."""
        result = normalize_per_100_possessions(20, 80)
        assert result == 25.0
    
    @pytest.mark.unit
    def test_calculate_per_100_minutes(self):
        """Test per 100 minutes calculation."""
        result = calculate_per_100_minutes(10, 25)
        assert result == 40.0
    
    @pytest.mark.unit
    def test_get_player_stats_averages_empty(self):
        """Test get_player_stats_averages with empty list."""
        result = get_player_stats_averages([])
        assert result is not None
