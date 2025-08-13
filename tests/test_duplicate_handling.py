import pytest
import pandas as pd
from app.services.bls_service import BLSDataValidator

class TestDuplicateHandling:
    """Test handling of duplicate SBLS in single file"""
    
    def test_duplicate_sbls_last_wins(self):
        """Test that last occurrence of duplicate SBLS wins"""
        validator = BLSDataValidator()
        df = pd.DataFrame({
            'SBLS': ['B123456', 'B789012', 'B123456'],  # B123456 appears twice
            'ST': ['Apfel v1', 'Birne', 'Apfel v2'],    # Different values
            'GCAL': [50, 60, 55]
        })
        
        valid_records, errors = validator.validate_dataframe(df, "test.txt")
        
        # Should have 3 valid records (duplicates handled at DB level)
        assert len(valid_records) == 3
        assert len(errors) == 0
        
        # Find the B123456 records
        b123456_records = [r for r in valid_records if r['SBLS'] == 'B123456']
        assert len(b123456_records) == 2
        
        # Last one should have 'Apfel v2' and GCAL=55
        last_record = b123456_records[-1]
        assert last_record['ST'] == 'Apfel v2'
        assert last_record['GCAL'] == 55.0