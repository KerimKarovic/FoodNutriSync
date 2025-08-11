# scripts/generate_typed_model_from_xlsx.py
import sys
import pandas as pd
from pathlib import Path

# Usage:
#   python scripts/generate_typed_model_from_xlsx.py "C:\path\BLS_3.02_Variablennamen_abgekuerzt_TESTDATENSATZ.xlsx"
#
# This will overwrite app/models.py with a typed columns model where:
# - Primary key = bls_number (CHAR(7) CHECK)
# - name_german = mapped from 'ST' in your import code later
# - All other columns from the XLSX header (except SBLS/ST/STE) become NUMERIC(10,3)
#
# DB column names stay UPPERCASE (matching BLS), Python attributes are lowercase.

HEADER_EXCLUSIONS = {"SBLS", "ST", "STE"}  # handled separately

TEMPLATE = '''\
from sqlalchemy import Column, String, CheckConstraint, Numeric
from app.database import Base

class BLSNutrition(Base):
    __tablename__ = "bls_nutrition"

    # Primary key: 1 letter (B–Y) + 6 digits
    bls_number = Column(String(7), primary_key=True, index=True)
    name_german = Column(String, nullable=False)

    __table_args__ = (
        CheckConstraint("bls_number ~ '^[B-Y][0-9]{{6}}$'", name="ck_bls_number_format"),
    )

{columns}
'''

def to_attr_name(code: str) -> str:
    # python attribute (lowercase). If starts with digit (unlikely), prefix with 'n_'.
    code = code.strip()
    attr = code.lower()
    if attr[0].isdigit():
        attr = f"n_{attr}"
    return attr

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_typed_model_from_xlsx.py <path_to_bls_header_excel>")
        sys.exit(1)

    xlsx_path = Path(sys.argv[1])
    if not xlsx_path.exists():
        print(f"File not found: {xlsx_path}")
        sys.exit(1)

    # Read first sheet, just need the columns
    df = pd.read_excel(xlsx_path, sheet_name=0, nrows=1)
    cols = [str(c).strip() for c in df.columns.tolist()]

    # Build NUMERIC(10,3) columns for all BLS nutrient codes except the excluded meta
    lines = []
    for code in cols:
        if code in HEADER_EXCLUSIONS:
            continue
        # keep DB column name EXACT as BLS (UPPERCASE) but python attribute lowercase
        attr = to_attr_name(code)
        # create Column("CODE", Numeric(10,3)) nullable True
        line = f'    {attr} = Column("{code}", Numeric(10, 3))'
        lines.append(line)

    body = "\n".join(lines)
    out = TEMPLATE.format(columns=body)

    # Write to app/models.py
    out_path = Path("app/models.py")
    out_path.write_text(out, encoding="utf-8")
    print(f"Wrote typed model with {len(lines)} nutrient columns to {out_path}")

if __name__ == "__main__":
    main()
