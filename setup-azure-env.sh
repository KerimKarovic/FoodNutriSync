#!/bin/bash
set -e

echo " Setting up Azure environment for NutriSync..."

# Variables
RESOURCE_GROUP="nutrisync-rg"
LOCATION="westeurope"
REGISTRY_NAME="nutrisyncregistry"  # Must be globally unique
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

echo " Using subscription: $SUBSCRIPTION_ID"

# Install Container Apps extension
echo " Installing Azure Container Apps extension..."
az extension add --name containerapp --upgrade

# Register providers
echo " Registering required providers..."
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

# Create resource group
echo " Creating resource group..."
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create Container Registry
echo " Creating Azure Container Registry..."
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $REGISTRY_NAME \
  --sku Basic \
  --admin-enabled true

# Get registry credentials
REGISTRY_SERVER=$(az acr show --name $REGISTRY_NAME --resource-group $RESOURCE_GROUP --query loginServer -o tsv)
REGISTRY_USERNAME=$(az acr credential show --name $REGISTRY_NAME --resource-group $RESOURCE_GROUP --query username -o tsv)
REGISTRY_PASSWORD=$(az acr credential show --name $REGISTRY_NAME --resource-group $RESOURCE_GROUP --query passwords[0].value -o tsv)

echo " Azure environment setup complete!"
echo ""
echo " Configuration Details:"
echo "Resource Group: $RESOURCE_GROUP"
echo "Registry Server: $REGISTRY_SERVER"
echo "Registry Username: $REGISTRY_USERNAME"
echo ""
echo " Update your deploy-azure.sh with:"
echo "CONTAINER_REGISTRY=\"$REGISTRY_SERVER\""
echo ""
echo " Now run: ./deploy-azure.sh"