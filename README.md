# **FoodNutriSync – BLS Nutrient Data Service**

## **Overview**
FoodNutriSync is a **standalone FastAPI backend** designed to store and serve nutrient data from the **Bundeslebensmittelschlüssel (BLS)** dataset.  
It allows importing the official BLS dataset into a PostgreSQL database and provides a clean, versioned API for retrieving nutrition data by **BLS number** or **food name**.

---

## **Features**
- **Single-table design** using PostgreSQL for optimal speed and simplicity.
- **Admin CSV Upload** for importing or updating the BLS dataset.
- **Search API** for looking up BLS entries by number or German name.
- **Validation Rules** to ensure data integrity (e.g., BLS number format check).
- **JSONB Storage** for 130+ nutrient values per food item.
- **Docker-ready** deployment for Azure Container Apps.

---

## **Tech Stack**
**Backend:**
- Python 3.10+
- FastAPI (async)
- SQLAlchemy + asyncpg
- Pydantic for data validation

**Database:**
- PostgreSQL (local development + Azure production)
- JSONB column for nutrient values

**Deployment:**
- Docker
- Azure Container Apps
- `.env` for local config, Azure Key Vault for production

**Frontend (Admin UI):**
- Minimal HTML/JavaScript
- Jinja2 templates (FastAPI)
- CSV upload form

---

## **Database Schema**
### **Table: `bls_nutrition`**
| Field        | Type      | Description                                   |
|--------------|-----------|-----------------------------------------------|
| bls_number   | TEXT (PK) | Unique 7-character code (1 letter + 6 digits) |
| name_german  | TEXT      | Official German food name                     |
| nutrients    | JSONB     | ~130 nutrient values for the food item        |

**Indexes:**
- Primary Key on `bls_number`
- Optional GIN index on `nutrients` for advanced filtering
- Index on `name_german` for fast search

---

## **API Endpoints**
### **Public Endpoints**
- `GET /bls/{bls_number}` – Fetch full nutrient data for a given BLS number.
- `GET /bls/search?name=<query>` – Search BLS entries by partial German name.

### **Admin Endpoints**
- `POST /admin/upload-bls` – Upload a BLS CSV file and update the database.
  - **Validation:**
    - Checks that `bls_number` matches `^[A-Z]\d{6}$` format.
    - Rejects rows with missing or invalid codes.
  - **Upsert Logic:** Updates existing entries or inserts new ones.
  - **Response:** Returns counts of added, updated, and failed rows.

---

## **Data Flow**
1. Admin uploads a BLS CSV file via `/admin/upload-bls`.
2. Backend parses CSV, validates data, and upserts into `bls_nutrition`.
3. API clients request nutrient data by BLS number or name.
4. Service responds with structured JSON containing all nutrient values.

---

## **Setup Instructions**
### 1. Clone the repository
```bash
git clone https://github.com/KerimKarovic/FoodNutriSync.git
cd FoodNutriSync
