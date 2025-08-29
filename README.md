# **FoodNutriSync – BLS Nutrient Data Service**

## **Overview**
FoodNutriSync is a **production-ready FastAPI backend** designed to store and serve nutrient data from the **Bundeslebensmittelschlüssel (BLS)** dataset.  
It provides a secure, JWT-authenticated API for retrieving nutrition data by **BLS number** or **food name**, with admin endpoints for data management.

---

## **Features**
- **PostgreSQL Database** with optimized schema for 134+ nutrient columns
- **JWT Authentication** via company LicenseManager integration
- **RESTful API** for BLS data lookup and search
- **Admin API** for CSV/TXT file uploads and bulk operations
- **Structured Logging** with JSON output for monitoring
- **Docker-ready** for Azure Container Apps deployment
- **Production Security** with CORS, input validation, and role-based access

---

## **Tech Stack**
**Backend:**
- Python 3.11+
- FastAPI (async)
- SQLAlchemy + asyncpg
- Pydantic for data validation
- JWT authentication
- Structured logging

**Database:**
- PostgreSQL with 134 nutrient columns
- Optimized indexes for fast lookups

**Deployment:**
- Docker container
- Azure Container Apps
- Environment-based configuration

---

## **Database Schema**
### **Table: `bls_nutrition`**
| Field        | Type      | Description                                   |
|--------------|-----------|-----------------------------------------------|
| bls_number   | TEXT (PK) | Unique 7-character code (1 letter + 6 digits) |
| name_german  | TEXT      | Official German food name                     |
| name_english | TEXT      | English food name (optional)                  |
| gcal, gj, etc| NUMERIC   | 130+ nutrient values per BLS specification   |

**Indexes:**
- Primary Key on `bls_number`
- Index on `name_german` for search performance
- Index on `name_english` for multilingual support

---

## **API Endpoints**

### **Public Endpoints** (Require JWT Authentication)
- `GET /bls/search?name=<query>&limit=<number>` – Search BLS entries by German name (limit 1-100)
- `GET /bls/{bls_number}` – Fetch full nutrient data for a BLS number
- `GET /health` – Basic health check endpoint
- `GET /health/live` – Kubernetes liveness probe with detailed status
- `GET /health/ready` – Kubernetes readiness probe with database connectivity

### **Admin Endpoints** (Require Admin Role)
- `PUT /admin/upload-bls` – Upload BLS dataset file and perform full database replacement
- `GET /admin` – Admin dashboard interface
- `GET /login` – Login page for JWT token authentication

### **Authentication Endpoints**
- `POST /auth/login` – Validate JWT token and set authentication cookie
- `POST /auth/logout` – Clear authentication session

### **Interactive Documentation** (Require Authentication)
- `GET /docs` – Protected Swagger UI for API testing
- `GET /redoc` – Protected alternative API documentation
- `GET /openapi.json` – Protected OpenAPI schema

---

## ** DEPLOYMENT INSTRUCTIONS FOR COMPANY IT**

### **1. Database Setup**
Create PostgreSQL database and user:
```sql
CREATE DATABASE nutrisync_prod;
CREATE USER nutrisync_app_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE nutrisync_prod TO nutrisync_app_user;
```

### **2. Environment Variables (Azure Container Apps)**
Configure these environment variables in Azure:

```env
# Database Connection
DATABASE_URL=postgresql+asyncpg://nutrisync_app_user:${DB_PASSWORD}@your-db-server:5432/nutrisync_prod
ALEMBIC_DATABASE_URL=postgresql+psycopg2://nutrisync_app_user:${DB_PASSWORD}@your-db-server:5432/nutrisync_prod

# JWT Authentication (Update with your LicenseManager details)
LICENSEMANAGER_PUBLIC_KEY_URL=https://your-licensemanager.company.com/public-key
LICENSEMANAGER_ISSUER=your-licensemanager.company.com
JWT_ALGORITHM=RS256
ALLOWED_ROLES=BLS-Data-Reader,Admin
ENVIRONMENT=production
```

### **3. CORS Configuration Update**
Update `app/main.py` with your frontend domains:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://your-frontend-domain.com",      # Your frontend
        "https://your-admin-portal.com",         # Admin interface
        "http://localhost:3000",                 # Keep for development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### **4. Database Migration**
After deployment, run database migration:
```bash
# Inside the container or via Azure Container Apps exec
alembic upgrade head
```

### **5. Initial Data Upload**
Upload BLS dataset via API:
```bash
# Use /docs interface or curl
curl -X PUT "https://your-api-domain.com/admin/upload-bls" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@bls_dataset.txt"
```

---

## ** Authentication & Authorization**

### **JWT Token Requirements**
- **Algorithm:** RS256
- **Required Claims:** `sub` (user ID), `roles` (array)
- **Required Roles:** 
  - `BLS-Data-Reader` - Access to search/lookup endpoints
  - `Admin` - Access to upload/management endpoints

### **Development Bypass**
Set `ENVIRONMENT=development` to bypass authentication for local testing.

---

## **  Monitoring & Logging**

### **Structured Logs**
- **Format:** JSON with timestamps, levels, and context
- **Location:** `/app/logs/app.log` in container
- **Events:** API calls, uploads, errors, database operations

### **Health Monitoring**
- **Endpoint:** `GET /health`
- **Response:** `{"status": "ok"}`

---

## ** Local Development**

### **Prerequisites**
- Python 3.11+
- PostgreSQL
- Git

### **Setup**
```bash
# Clone repository
git clone <repository-url>
cd FoodNutriSync

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your local database settings

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### **Testing**
```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app
```

---

## ** Project Structure**
```
FoodNutriSync/
├── app/
│   ├── main.py              # FastAPI application
│   ├── auth.py              # JWT authentication
│   ├── database.py          # Database connection
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── logging_config.py    # Structured logging
│   └── services/
│       └── bls_service.py   # Business logic
├── alembic/                 # Database migrations
├── tests/                   # Test suite
├── Dockerfile              # Container configuration
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

---

## **🔧 Configuration Files to Update**

1. **CORS Origins** in `app/main.py`
2. **Environment Variables** in Azure Container Apps
3. **Database Connection** via environment variables
4. **JWT Settings** via environment variables

---

## ** Support**

**API Documentation:** Available at `/docs` endpoint after deployment.
