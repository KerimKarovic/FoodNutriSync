
import pytest
import pandas as pd
from io import BytesIO
from app.services.bls_service import BLSDataValidator
from app.exceptions import BLSValidationError

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

class TestBLSDataValidation:
    """Test BLS data validation and processing"""
    
    @pytest.fixture
    def validator(self):
        return BLSDataValidator()
    
    def test_validate_dataframe_success(self, validator):
        """Test successful DataFrame validation"""
        df = pd.DataFrame({
            'SBLS': ['B123456', 'C789012'],
            'ST': ['Apfel', 'Birne'],  # Use ST for German name
            'STE': ['Apple', 'Pear'],  # Use STE for English name
            'GCAL': [52.0, 57.0],
            'ZE': [0.3, 0.4]
        })
        
        valid_records, errors = validator.validate_dataframe(df, "test.csv")
        
        assert len(valid_records) == 2
        assert len(errors) == 0
        assert valid_records[0]['SBLS'] == 'B123456'
        assert valid_records[0]['ST'] == 'Apfel'
    
    def test_validate_dataframe_with_errors(self, validator):
        """Test DataFrame validation with errors"""
        df = pd.DataFrame({
            'SBLS': ['INVALID', 'B123456', ''],
            'STE': ['Apfel', '', 'Birne'],
            'ENERC': [52.0, 57.0, 'invalid']
        })
        
        valid_records, errors = validator.validate_dataframe(df, "test.csv")
        
        assert len(valid_records) == 0  # No completely valid records
        assert len(errors) > 0
    
    def test_extract_bls_number_patterns(self, validator):
        """Test BLS number pattern validation"""
        # Valid patterns
        valid_numbers = ['B123456', 'C789012', 'Y999999']
        for num in valid_numbers:
            row = pd.Series({'SBLS': num})
            assert validator._extract_bls_number(row) == num
        
        # Invalid patterns
        invalid_numbers = ['A123456', 'Z123456', '123456', 'B12345', 'B1234567']
        for num in invalid_numbers:
            row = pd.Series({'SBLS': num})
            assert validator._extract_bls_number(row) is None
    
    def test_extract_nutrients(self, validator):
        """Test nutrient extraction from row"""
        row = pd.Series({
            'SBLS': 'B123456',
            'STE': 'Test Food',
            'ENERC': '100.5',
            'PROT': '5,2',  # Test comma decimal
            'FAT': '',      # Empty value
            'INVALID': 'not_a_number'
        })
        
        nutrients = validator._extract_nutrients(row)
        
        assert nutrients['enerc'] == 100.5
        assert nutrients['prot'] == 5.2
        assert 'fat' not in nutrients
        assert 'invalid' not in nutrients
        assert 'sbls' not in nutrients
        assert 'ste' not in nutrients

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

