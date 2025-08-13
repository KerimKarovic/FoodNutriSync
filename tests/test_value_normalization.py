import pytest
import pandas as pd
from app.services.bls_service import BLSDataValidator

class TestValueNormalization:
    """Test numeric value parsing and normalization"""
    
    @pytest.mark.parametrize("input_value,expected", [
        ("1,23", 1.23),
        ("1.234,56", 1234.56),  # German format: thousand separator . decimal ,
        ("52", 52.0),
        ("0,0", 0.0),
        ("", None),  # Empty
        ("-", None),  # Dash
        ("—", None),  # Em dash
        ("k.A.", None),  # German "keine Angabe"
        ("n.a.", None),  # Not available
        ("invalid", None),  # Invalid text
        ("-5,2", None),  # Negative (should be rejected)
    ])
    def test_numeric_normalization(self, input_value, expected):
        """Test various numeric formats"""
        validator = BLSDataValidator()
        row = pd.Series({
            'SBLS': 'B123456',
            'ST': 'Test',
            'GCAL': input_value
        })
        
        nutrients = validator._extract_nutrients(row)
        
        if expected is None:
            assert 'GCAL' not in nutrients
        else:
            assert nutrients['GCAL'] == expected
            print(f"DEBUG: Expected {expected}, got {nutrients.get('GCAL')}")

    def test_multiple_comma_decimals(self):
        """Test row with multiple comma decimal values"""
        validator = BLSDataValidator()
        row = pd.Series({
            'SBLS': 'B123456',
            'ST': 'Test',
            'GCAL': '100,5',
            'ZE': '5,2',
            'ZF': '1,23'
        })
        
        nutrients = validator._extract_nutrients(row)
        
        assert nutrients['GCAL'] == 100.5
        assert nutrients['ZE'] == 5.2
        assert nutrients['ZF'] == 1.23
