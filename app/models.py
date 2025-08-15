from sqlalchemy import Column, String, CheckConstraint, Numeric, Index
from app.database import Base

class BLSNutrition(Base):
    __tablename__ = "bls_nutrition"

    # Core identification (first 3 columns in correct BLS order)
    bls_number   = Column("SBLS", String(7), primary_key=True, index=True)   
    name_german  = Column("ST",   String,     nullable=False, index=True)   
    name_english = Column("STE",  String,     nullable=True,  index=True)    
    
    # Energy values (columns 4-7)
    gcal = Column("GCAL", Numeric(10, 3))
    gj = Column("GJ", Numeric(10, 3))
    gcalzb = Column("GCALZB", Numeric(10, 3))
    gjzb = Column("GJZB", Numeric(10, 3))
    
    # Basic nutrients (columns 8-15)
    zw = Column("ZW", Numeric(10, 3))  # Water
    ze = Column("ZE", Numeric(10, 3))  # Protein
    zf = Column("ZF", Numeric(10, 3))  # Fat
    zk = Column("ZK", Numeric(10, 3))  # Carbohydrates
    zb = Column("ZB", Numeric(10, 3))  # Fiber
    zm = Column("ZM", Numeric(10, 3))  # Minerals
    zo = Column("ZO", Numeric(10, 3))  # Organic acids
    za = Column("ZA", Numeric(10, 3))  # Ash
    
    # Vitamins (columns 16-31)
    va = Column("VA", Numeric(10, 3))
    var = Column("VAR", Numeric(10, 3))
    vac = Column("VAC", Numeric(10, 3))
    vd = Column("VD", Numeric(10, 3))
    ve = Column("VE", Numeric(10, 3))
    veat = Column("VEAT", Numeric(10, 3))
    vk = Column("VK", Numeric(10, 3))
    vb1 = Column("VB1", Numeric(10, 3))
    vb2 = Column("VB2", Numeric(10, 3))
    vb3 = Column("VB3", Numeric(10, 3))
    vb3a = Column("VB3A", Numeric(10, 3))
    vb5 = Column("VB5", Numeric(10, 3))
    vb6 = Column("VB6", Numeric(10, 3))
    vb7 = Column("VB7", Numeric(10, 3))
    vb9g = Column("VB9G", Numeric(10, 3))
    vb12 = Column("VB12", Numeric(10, 3))
    vc = Column("VC", Numeric(10, 3))
    
    # Minerals (columns 32-44)
    mna = Column("MNA", Numeric(10, 3))  # Sodium
    mk = Column("MK", Numeric(10, 3))    # Potassium
    mca = Column("MCA", Numeric(10, 3))  # Calcium
    mmg = Column("MMG", Numeric(10, 3))  # Magnesium
    mp = Column("MP", Numeric(10, 3))    # Phosphorus
    ms = Column("MS", Numeric(10, 3))    # Sulfur
    mcl = Column("MCL", Numeric(10, 3))  # Chlorine
    mfe = Column("MFE", Numeric(10, 3))  # Iron
    mzn = Column("MZN", Numeric(10, 3))  # Zinc
    mcu = Column("MCU", Numeric(10, 3))  # Copper
    mmn = Column("MMN", Numeric(10, 3))  # Manganese
    mf = Column("MF", Numeric(10, 3))    # Fluorine
    mj = Column("MJ", Numeric(10, 3))    # Iodine
    
    # K-series nutrients (columns 45-67)
    kam = Column("KAM", Numeric(10, 3))
    kas = Column("KAS", Numeric(10, 3))
    kax = Column("KAX", Numeric(10, 3))
    ka = Column("KA", Numeric(10, 3))
    kmt = Column("KMT", Numeric(10, 3))
    kmf = Column("KMF", Numeric(10, 3))
    kmg = Column("KMG", Numeric(10, 3))
    km = Column("KM", Numeric(10, 3))
    kds = Column("KDS", Numeric(10, 3))
    kdm = Column("KDM", Numeric(10, 3))
    kdl = Column("KDL", Numeric(10, 3))
    kd = Column("KD", Numeric(10, 3))
    kmd = Column("KMD", Numeric(10, 3))
    kpor = Column("KPOR", Numeric(10, 3))
    kpon = Column("KPON", Numeric(10, 3))
    kpg = Column("KPG", Numeric(10, 3))
    kps = Column("KPS", Numeric(10, 3))
    kp = Column("KP", Numeric(10, 3))
    kbp = Column("KBP", Numeric(10, 3))
    kbh = Column("KBH", Numeric(10, 3))
    kbu = Column("KBU", Numeric(10, 3))
    kbc = Column("KBC", Numeric(10, 3))
    kbl = Column("KBL", Numeric(10, 3))
    kbw = Column("KBW", Numeric(10, 3))
    kbn = Column("KBN", Numeric(10, 3))
    
    # E-series amino acids (columns 68-87)
    eile = Column("EILE", Numeric(10, 3))
    eleu = Column("ELEU", Numeric(10, 3))
    elys = Column("ELYS", Numeric(10, 3))
    emet = Column("EMET", Numeric(10, 3))
    ecys = Column("ECYS", Numeric(10, 3))
    ephe = Column("EPHE", Numeric(10, 3))
    etyr = Column("ETYR", Numeric(10, 3))
    ethr = Column("ETHR", Numeric(10, 3))
    etrp = Column("ETRP", Numeric(10, 3))
    eval = Column("EVAL", Numeric(10, 3))
    earg = Column("EARG", Numeric(10, 3))
    ehis = Column("EHIS", Numeric(10, 3))
    eea = Column("EEA", Numeric(10, 3))
    eala = Column("EALA", Numeric(10, 3))
    easp = Column("EASP", Numeric(10, 3))
    eglu = Column("EGLU", Numeric(10, 3))
    egly = Column("EGLY", Numeric(10, 3))
    epro = Column("EPRO", Numeric(10, 3))
    eser = Column("ESER", Numeric(10, 3))
    ena = Column("ENA", Numeric(10, 3))
    eh = Column("EH", Numeric(10, 3))
    ep = Column("EP", Numeric(10, 3))
    
    # F-series fatty acids (columns 88-130)
    f40 = Column("F40", Numeric(10, 3))
    f60 = Column("F60", Numeric(10, 3))
    f80 = Column("F80", Numeric(10, 3))
    f100 = Column("F100", Numeric(10, 3))
    f120 = Column("F120", Numeric(10, 3))
    f140 = Column("F140", Numeric(10, 3))
    f150 = Column("F150", Numeric(10, 3))
    f160 = Column("F160", Numeric(10, 3))
    f170 = Column("F170", Numeric(10, 3))
    f180 = Column("F180", Numeric(10, 3))
    f200 = Column("F200", Numeric(10, 3))
    f220 = Column("F220", Numeric(10, 3))
    f240 = Column("F240", Numeric(10, 3))
    fs = Column("FS", Numeric(10, 3))
    f141 = Column("F141", Numeric(10, 3))
    f151 = Column("F151", Numeric(10, 3))
    f161 = Column("F161", Numeric(10, 3))
    f171 = Column("F171", Numeric(10, 3))
    f181 = Column("F181", Numeric(10, 3))
    f201 = Column("F201", Numeric(10, 3))
    f221 = Column("F221", Numeric(10, 3))
    f241 = Column("F241", Numeric(10, 3))
    fu = Column("FU", Numeric(10, 3))
    f162 = Column("F162", Numeric(10, 3))
    f164 = Column("F164", Numeric(10, 3))
    f182 = Column("F182", Numeric(10, 3))
    f183 = Column("F183", Numeric(10, 3))
    f184 = Column("F184", Numeric(10, 3))
    f193 = Column("F193", Numeric(10, 3))
    f202 = Column("F202", Numeric(10, 3))
    f203 = Column("F203", Numeric(10, 3))
    f204 = Column("F204", Numeric(10, 3))
    f205 = Column("F205", Numeric(10, 3))
    f222 = Column("F222", Numeric(10, 3))
    f223 = Column("F223", Numeric(10, 3))
    f224 = Column("F224", Numeric(10, 3))
    f225 = Column("F225", Numeric(10, 3))
    f226 = Column("F226", Numeric(10, 3))
    fp = Column("FP", Numeric(10, 3))
    fk = Column("FK", Numeric(10, 3))
    fm = Column("FM", Numeric(10, 3))
    fl = Column("FL", Numeric(10, 3))
    fo3 = Column("FO3", Numeric(10, 3))
    fo6 = Column("FO6", Numeric(10, 3))
    fg = Column("FG", Numeric(10, 3))
    fc = Column("FC", Numeric(10, 3))
    
    # G-series (final columns 131-134)
    gfps = Column("GFPS", Numeric(10, 3))
    gkb = Column("GKB", Numeric(10, 3))
    gmko = Column("GMKO", Numeric(10, 3))
    gp = Column("GP", Numeric(10, 3))
    
    __table_args__ = (
        CheckConstraint('"SBLS" ~ \'^[B-Y][0-9]{6}$\'', name="ck_bls_number_format"),
        Index(
            'ix_blsnutrition_ST_trgm',
            'ST',
            postgresql_using='gin',
            postgresql_ops={'ST': 'gin_trgm_ops'},
        ),
        Index(
            'ix_blsnutrition_STE_trgm',
            'STE',
            postgresql_using='gin',
            postgresql_ops={'STE': 'gin_trgm_ops'},
        ),
    )
