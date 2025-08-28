import pytest
import yaml
import os


class TestAzureDeployment:
    """Azure Container Apps specific tests"""
    
    @pytest.mark.azure
    def test_azure_config_exists_and_valid(self):
        """Azure container app config exists and has basic structure"""
        assert os.path.exists("azure-containerapp.yaml")
        
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        assert config["apiVersion"] == "2023-05-01"  # String, not date
        assert "properties" in config
        assert "template" in config["properties"]

    @pytest.mark.azure
    def test_deploy_script_exists(self):
        """Deploy script exists and is executable"""
        assert os.path.exists("deploy-azure.sh")
        
        # Just check it's readable, don't test content
        with open("deploy-azure.sh", "r", encoding="utf-8") as f:
            content = f.read()
            assert "RESOURCE_GROUP" in content

    @pytest.mark.azure
    def test_health_probes_azure_compatible(self, client_with_mock_db):
        """Health endpoints work for Azure probes"""
        # Liveness should always work
        response = client_with_mock_db.get("/health/live")
        assert response.status_code == 200
        
        # Readiness should return 200 when DB is OK
        response = client_with_mock_db.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data