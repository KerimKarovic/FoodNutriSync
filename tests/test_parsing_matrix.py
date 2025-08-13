import pytest
from io import BytesIO
import pandas as pd
from app.services.bls_service import BLSDataValidator

class TestParsingMatrix:
    """Test various file format combinations"""
    
    @pytest.mark.parametrize("delimiter,content", [
        ("\t", "SBLS\tST\tGCAL\nB123456\tApfel\t52"),
        (";", "SBLS;ST;GCAL\nB123456;Apfel;52"),
        (",", "SBLS,ST,GCAL\nB123456,Apfel,52")
    ])
    def test_delimiter_variations(self, delimiter, content):
        """Test different delimiters"""
        df = pd.read_csv(BytesIO(content.encode()), sep=delimiter)
        validator = BLSDataValidator()
        valid_records, errors = validator.validate_dataframe(df, "test.txt")
        
        assert len(valid_records) == 1
        assert len(errors) == 0
        assert valid_records[0]['SBLS'] == 'B123456'
    
    @pytest.mark.parametrize("encoding,bom", [
        ("utf-8", False),
        ("utf-8-sig", True),
        ("latin-1", False),
        ("windows-1252", False)
    ])
    def test_encoding_variations(self, encoding, bom):
        """Test different encodings"""
        content = "SBLS\tST\tGCAL\nB123456\tÄpfel\t52"
        encoded = content.encode(encoding)
        
        df = pd.read_csv(BytesIO(encoded), sep='\t', encoding=encoding)
        validator = BLSDataValidator()
        valid_records, errors = validator.validate_dataframe(df, "test.txt")
        
        assert len(valid_records) == 1
        assert valid_records[0]['ST'] == 'Äpfel'
    
    @pytest.mark.parametrize("header_variant", [
        "SBLS\tST\tGCAL",  # Normal
        " SBLS \t ST \t GCAL ",  # Spaces
        "SBLS\tST\tGCAL\t",  # Trailing tab
        "\ufeffSBLS\tST\tGCAL"  # BOM prefix
    ])
    def test_header_normalization(self, header_variant):
        """Test header cleaning"""
        content = f"{header_variant}\nB123456\tApfel\t52"
        df = pd.read_csv(BytesIO(content.encode('utf-8-sig')), sep='\t')
        
        # Clean headers like in main.py
        df.columns = [col.lstrip('ÿþ\ufeff').strip() for col in df.columns]
        
        validator = BLSDataValidator()
        valid_records, errors = validator.validate_dataframe(df, "test.txt")
        
        assert len(valid_records) == 1
        assert 'SBLS' in df.columns