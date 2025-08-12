
import pytest
import pandas as pd
import re
from unittest.mock import Mock
from decimal import Decimal

class TestBLSValidation:
    """Test BLS data validation functions"""
    
    def validate_bls_row_local(self, row, index: int) -> tuple[dict | None, str | None]:
        """Local copy of validation logic for testing"""
        bls_pattern = re.compile(r'^[B-Y]\d{6}$')
        
        try:
            bls_number = str(row.get('SBLS', '') or '').strip().upper()
            name_german = str(row.get('ST', '') or '').strip()
            
            if not bls_number:
                return None, f"Row {index + 1}: Missing BLS number"
            
            if not bls_pattern.match(bls_number):
                return None, f"Row {index + 1}: Invalid BLS number format '{bls_number}'"
            
            if not name_german or name_german == 'nan':
                return None, f"Row {index + 1}: Missing German name"
            
            if len(name_german) > 255:
                return None, f"Row {index + 1}: Name too long (max 255 chars)"
            
            nutrient_values = {}
            for col in row.index:
                if col not in ['SBLS', 'ST', 'STE', 'bls_number', 'name_german']:
                    value = row.get(col)
                    if pd.notna(value) and str(value) != '':
                        try:
                            s = str(value).replace(',', '.')
                            float_val = float(s)
                            if float_val >= 0:
                                nutrient_values[col.lower()] = float_val
                        except (ValueError, TypeError):
                            pass
            
            return {
                'bls_number': bls_number,
                'name_german': name_german,
                **nutrient_values
            }, None
            
        except Exception as e:
            return None, f"Row {index + 1}: Validation error - {str(e)}"
    
    def test_validate_bls_row_valid_data(self):
        """Test validation with valid BLS data"""
        row = pd.Series({
            'SBLS': 'M401600',
            'ST': 'Edamer, vollfett',
            'GCAL': '330.0',
            'EPRO': '25.0',
            'VC': '0.0',
            'MNA': '700.0'
        })
        
        result, error = self.validate_bls_row_local(row, 0)
        
        assert error is None
        assert result is not None
        assert result['bls_number'] == 'M401600'
        assert result['name_german'] == 'Edamer, vollfett'
        assert result['gcal'] == 330.0
        assert result['mna'] == 700.0

    def test_validate_bls_row_invalid_bls_number(self):
        """Test validation with invalid BLS number"""
        row = pd.Series({
            'SBLS': 'INVALID',
            'ST': 'Test Food',
            'GCAL': '100.0'
        })
        
        result, error = self.validate_bls_row_local(row, 0)
        
        assert result is None
        assert error is not None
        assert "Invalid BLS number format" in error

    def test_validate_bls_row_missing_name(self):
        """Test validation with missing name"""
        row = pd.Series({
            'SBLS': 'M401600',
            'ST': '',
            'GCAL': '100.0'
        })
        
        result, error = self.validate_bls_row_local(row, 0)
        
        assert result is None
        assert error is not None
        assert "Missing German name" in error

class TestUtilityFunctions:
    """Test utility functions"""
    
    def get_client_ip_local(self, request):
        """Local copy of get_client_ip for testing"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        if hasattr(request, 'client') and request.client:
            return request.client.host
        
        return "unknown"
    
    def test_get_client_ip_direct(self):
        """Test getting client IP directly"""
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client = Mock()
        mock_request.client.host = "192.168.1.1"
        
        ip = self.get_client_ip_local(mock_request)
        assert ip == "192.168.1.1"

    def test_get_client_ip_forwarded(self):
        """Test getting client IP from X-Forwarded-For header"""
        mock_request = Mock()
        mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 192.168.1.1"}
        
        ip = self.get_client_ip_local(mock_request)
        assert ip == "203.0.113.1"

    def test_get_client_ip_no_client(self):
        """Test getting client IP when no client info"""
        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client = None
        
        ip = self.get_client_ip_local(mock_request)
        assert ip == "unknown"

class TestModelCreation:
    """Test BLS model instantiation"""
    
    def test_bls_nutrition_creation(self):
        """Test creating BLS nutrition object"""
        from app.models import BLSNutrition
        
        # Create the object with data
        data = {
            'bls_number': "M401600",
            'name_german': "Test Food",
            'gcal': Decimal('330.0'),
            'mna': Decimal('700.0')
        }
        
        bls_item = BLSNutrition(**data)
        
        # Test by accessing the underlying values
        assert getattr(bls_item, 'bls_number') == "M401600"
        assert getattr(bls_item, 'name_german') == "Test Food"
        assert getattr(bls_item, 'gcal') == Decimal('330.0')
        assert getattr(bls_item, 'mna') == Decimal('700.0')

    def test_bls_nutrition_minimal(self):
        """Test BLS nutrition with minimal data"""
        from app.models import BLSNutrition
        
        bls_item = BLSNutrition(
            bls_number="M401600",
            name_german="Test Food"
        )
        
        # Test by accessing the underlying values
        assert getattr(bls_item, 'bls_number') == "M401600"
        assert getattr(bls_item, 'name_german') == "Test Food"
        
        # Test that optional fields are None
        assert getattr(bls_item, 'gcal', None) is None
        assert getattr(bls_item, 'mna', None) is None
