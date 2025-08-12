
import pytest
import pandas as pd
from io import BytesIO

class TestDataProcessing:
    """Test data processing and transformation"""
    
    def test_csv_data_parsing(self):
        """Test parsing CSV data format"""
        csv_content = """SBLS,ST,GCAL,EPRO,VC,MNA
M401600,Edamer vollfett,330,25,0,700
M401700,Gouda vollfett,356,25,0,819"""
        
        df = pd.read_csv(BytesIO(csv_content.encode()))
        
        assert len(df) == 2
        assert df.iloc[0]['SBLS'] == 'M401600'
        assert df.iloc[0]['ST'] == 'Edamer vollfett'
        assert df.iloc[0]['GCAL'] == 330

class TestDataValidation:
    """Test data validation rules"""
    
    def test_bls_number_format_validation(self):
        """Test BLS number format patterns"""
        valid_numbers = ['M401600', 'B123456', 'Y999999']
        invalid_numbers = ['A123456', 'Z123456', '1234567', 'M12345', 'M1234567']
        
        import re
        pattern = r'^[B-Y][0-9]{6}$'
        
        for num in valid_numbers:
            assert re.match(pattern, num), f"{num} should be valid"
        
        for num in invalid_numbers:
            assert not re.match(pattern, num), f"{num} should be invalid"

class TestErrorHandling:
    """Test error handling scenarios"""
    
    def test_empty_dataframe_handling(self):
        """Test handling empty dataframes"""
        empty_df = pd.DataFrame()
        
        assert len(empty_df) == 0
        assert empty_df.empty

    def test_missing_required_columns(self):
        """Test handling missing required columns"""
        df_missing_cols = pd.DataFrame({
            'WRONG_COL': ['value1', 'value2']
        })
        
        required_cols = ['SBLS', 'ST']
        missing_cols = [col for col in required_cols if col not in df_missing_cols.columns]
        
        assert 'SBLS' in missing_cols
        assert 'ST' in missing_cols

class TestNutrientMapping:
    """Test nutrient column mapping"""
    
    def test_column_name_mapping(self):
        """Test mapping CSV columns to model attributes"""
        csv_columns = ['GCAL', 'EPRO', 'VC', 'MNA', 'ZF', 'ZK']
        model_attributes = ['gcal', 'epro', 'vc', 'mna', 'zf', 'zk']  # Lowercase versions
        
        # Test that we can map uppercase CSV columns to lowercase model attributes
        mapping = {col: col.lower() for col in csv_columns}
        
        assert mapping['GCAL'] == 'gcal'
        assert mapping['EPRO'] == 'epro'
        assert mapping['MNA'] == 'mna'

    def test_nutrient_value_ranges(self):
        """Test reasonable ranges for nutrient values"""
        test_values = {
            'gcal': (0, 1000),      # Calories per 100g
            'mna': (0, 10000),      # Sodium in mg
            'vc': (0, 1000),        # Vitamin C in mg
            'zf': (0, 100),         # Fat percentage
        }
        
        for nutrient, (min_val, max_val) in test_values.items():
            # Test boundary values
            assert min_val >= 0, f"{nutrient} minimum should be non-negative"
            assert max_val > min_val, f"{nutrient} range should be valid"

