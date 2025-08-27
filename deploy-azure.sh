#!/bin/bash
set -e

# Configuration
RESOURCE_GROUP="nutrisync-rg"
LOCATION="westeurope"
CONTAINER_APP_ENV="nutrisync-env"
CONTAINER_APP_NAME="nutrisync-api"
DB_SERVER_NAME="nutrisync-db-server"
DB_NAME="nutrisync_db"
DB_USER="nutrisync"
CONTAINER_REGISTRY="your-registry.azurecr.io"  # Update this
IMAGE_NAME="nutrisync-api"
IMAGE_TAG="latest"

echo "🚀 Deploying NutriSync BLS API to Azure Container Apps..."

# Create resource group
echo "📦 Creating resource group..."
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create PostgreSQL server
echo "🗄️ Creating PostgreSQL server..."
az postgres flexible-server create \
  --name $DB_SERVER_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --admin-user $DB_USER \
  --admin-password "NutriSync2024!" \
  --database-name $DB_NAME \
  --sku-name Standard_B1ms \
  --storage-size 32 \
  --version 15

# Configure firewall for Azure services
echo "🔧 Configuring database firewall..."
az postgres flexible-server firewall-rule create \
  --name $DB_SERVER_NAME \
  --resource-group $RESOURCE_GROUP \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

# Create Container App Environment
echo "🌐 Creating Container App Environment..."
az containerapp env create \
  --name $CONTAINER_APP_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Build and push container image
echo "🐳 Building and pushing container image..."
az acr build \
  --registry $CONTAINER_REGISTRY \
  --image $IMAGE_NAME:$IMAGE_TAG \
  .

# Create Container App
echo "🚀 Creating Container App..."
az containerapp create \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_ENV \
  --image $CONTAINER_REGISTRY/$IMAGE_NAME:$IMAGE_TAG \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 0.5 \
  --memory 1Gi \
  --env-vars \
    DATABASE_URL="postgresql+asyncpg://$DB_USER:NutriSync2024!@$DB_SERVER_NAME.postgres.database.azure.com:5432/$DB_NAME" \
    ALEMBIC_DATABASE_URL="postgresql+psycopg2://$DB_USER:NutriSync2024!@$DB_SERVER_NAME.postgres.database.azure.com:5432/$DB_NAME" \
    ENVIRONMENT="production" \
    LOG_LEVEL="INFO"

# Get the app URL
APP_URL=$(az containerapp show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --query properties.configuration.ingress.fqdn -o tsv)

echo "✅ Deployment complete!"
echo "🌐 API URL: https://$APP_URL"
echo "📚 API Docs: https://$APP_URL/docs"
echo "❤️ Health Check: https://$APP_URL/health"

# Run database migration
echo "🔄 Running database migrations..."
az containerapp exec \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --command "alembic upgrade head"

echo "🎉 NutriSync BLS API is now live on Azure!"