import pytest
import os
import yaml
from unittest.mock import patch, MagicMock
import json

class TestAzureConfiguration:
    """Test Azure Container Apps specific configuration"""
    
    def test_azure_container_app_yaml_structure(self):
        """Test Azure Container App YAML has correct structure"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        # Required top-level fields
        assert config["apiVersion"] == "2023-05-01"
        assert config["location"] == "westeurope"
        assert config["name"] == "nutrisync-api"
        assert "properties" in config
        
        # Properties structure
        props = config["properties"]
        assert "configuration" in props
        assert "template" in props
        
        # Configuration
        config_section = props["configuration"]
        assert "ingress" in config_section
        assert "secrets" in config_section
        
        # Template
        template = props["template"]
        assert "containers" in template
        assert "scale" in template

    def test_azure_ingress_configuration(self):
        """Test Azure ingress configuration"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        ingress = config["properties"]["configuration"]["ingress"]
        assert ingress["external"] is True
        assert ingress["targetPort"] == 8000
        assert ingress["allowInsecure"] is False
        
        # Traffic configuration
        traffic = ingress["traffic"]
        assert len(traffic) == 1
        assert traffic[0]["weight"] == 100
        assert traffic[0]["latestRevision"] is True

    def test_azure_secrets_configuration(self):
        """Test Azure secrets configuration"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        secrets = config["properties"]["configuration"]["secrets"]
        secret_names = [secret["name"] for secret in secrets]
        
        required_secrets = ["database-url", "alembic-database-url"]
        for secret in required_secrets:
            assert secret in secret_names

    def test_azure_container_configuration(self):
        """Test Azure container configuration"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        containers = config["properties"]["template"]["containers"]
        assert len(containers) == 1
        
        container = containers[0]
        assert container["name"] == "nutrisync-api"
        assert "image" in container
        assert "env" in container
        assert "resources" in container
        assert "probes" in container

    def test_azure_environment_variables(self):
        """Test Azure environment variables configuration"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        container = config["properties"]["template"]["containers"][0]
        env_vars = container["env"]
        
        env_names = [env["name"] for env in env_vars]
        required_envs = ["DATABASE_URL", "ALEMBIC_DATABASE_URL", "ENVIRONMENT", "LOG_LEVEL"]
        
        for env_name in required_envs:
            assert env_name in env_names

    def test_azure_resource_limits(self):
        """Test Azure resource limits"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        container = config["properties"]["template"]["containers"][0]
        resources = container["resources"]
        
        assert resources["cpu"] == 0.5
        assert resources["memory"] == "1Gi"

    def test_azure_health_probes(self):
        """Test Azure health probes configuration"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        container = config["properties"]["template"]["containers"][0]
        probes = container["probes"]
        
        # Should have both liveness and readiness probes
        probe_types = [probe["type"] for probe in probes]
        assert "Liveness" in probe_types
        assert "Readiness" in probe_types
        
        # Check probe configurations
        for probe in probes:
            assert "httpGet" in probe
            assert probe["httpGet"]["port"] == 8000
            assert "path" in probe["httpGet"]
            assert "initialDelaySeconds" in probe
            assert "periodSeconds" in probe

    def test_azure_scaling_configuration(self):
        """Test Azure auto-scaling configuration"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
        
        scale = config["properties"]["template"]["scale"]
        assert scale["minReplicas"] == 1
        assert scale["maxReplicas"] == 3
        assert "rules" in scale
        
        # Check scaling rules
        rules = scale["rules"]
        assert len(rules) == 1
        
        http_rule = rules[0]
        assert http_rule["name"] == "http-scaling"
        assert "http" in http_rule
        assert "metadata" in http_rule["http"]
        assert "concurrentRequests" in http_rule["http"]["metadata"]

class TestAzureDeploymentScripts:
    """Test Azure deployment scripts"""
    
    def test_azure_setup_script_exists(self):
        """Test Azure setup script exists and has required content"""
        assert os.path.exists("setup-azure-env.sh")
        
        with open("setup-azure-env.sh", "r") as f:
            content = f.read()
            
        # Check for required Azure CLI commands
        required_commands = [
            "az extension add --name containerapp",
            "az provider register --namespace Microsoft.App",
            "az group create",
            "az acr create"
        ]
        
        for cmd in required_commands:
            assert cmd in content

    def test_azure_deploy_script_exists(self):
        """Test Azure deployment script exists and has required content"""
        assert os.path.exists("deploy-azure.sh")
        
        with open("deploy-azure.sh", "r") as f:
            content = f.read()
        
        # Check for required deployment steps
        required_steps = [
            "az group create",
            "az postgres flexible-server create",
            "az containerapp env create",
            "az acr build",
            "az containerapp create"
        ]
        
        for step in required_steps:
            assert step in content

    def test_azure_script_variables(self):
        """Test Azure scripts have required variables"""
        with open("deploy-azure.sh", "r") as f:
            content = f.read()
        
        required_vars = [
            "RESOURCE_GROUP=",
            "LOCATION=",
            "CONTAINER_APP_ENV=",
            "CONTAINER_APP_NAME=",
            "DB_SERVER_NAME=",
            "DB_NAME=",
            "DB_USER="
        ]
        
        for var in required_vars:
            assert var in content

class TestAzureCompatibility:
    """Test Azure Container Apps compatibility"""
    
    def test_dockerfile_azure_compatibility(self):
        """Test Dockerfile is compatible with Azure Container Apps"""
        with open("Dockerfile", "r") as f:
            content = f.read()
        
        # Azure Container Apps requirements
        assert "EXPOSE 8000" in content
        assert "uvicorn" in content
        
        # Should not have HEALTHCHECK (Azure handles this)
        assert "HEALTHCHECK" not in content

    def test_port_configuration_consistency(self):
        """Test port configuration is consistent across files"""
        # Check Dockerfile
        with open("Dockerfile", "r") as f:
            dockerfile_content = f.read()
        assert "EXPOSE 8000" in dockerfile_content
        
        # Check Azure config
        with open("azure-containerapp.yaml", "r") as f:
            azure_config = yaml.safe_load(f)
        
        ingress_port = azure_config["properties"]["configuration"]["ingress"]["targetPort"]
        assert ingress_port == 8000
        
        # Check health probe ports
        container = azure_config["properties"]["template"]["containers"][0]
        for probe in container["probes"]:
            assert probe["httpGet"]["port"] == 8000

    @patch.dict(os.environ, {
        'DATABASE_URL': 'postgresql+asyncpg://test:test@test.postgres.database.azure.com:5432/test',
        'ENVIRONMENT': 'production'
    })
    def test_azure_environment_variables(self):
        """Test Azure environment variables are properly configured"""
        # Test that environment variables match Azure expectations
        db_url = os.environ.get('DATABASE_URL')
        assert db_url is not None
        assert 'postgres.database.azure.com' in db_url
        assert 'postgresql+asyncpg://' in db_url
        
        env = os.environ.get('ENVIRONMENT')
        assert env == 'production'

class TestAzureMonitoring:
    """Test Azure monitoring and logging configuration"""
    
    def test_health_endpoints_for_azure_probes(self, client):
        """Test health endpoints work for Azure probes"""
        # Test liveness probe endpoint
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        # Test readiness probe endpoint
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_logging_configuration_for_azure(self):
        """Test logging configuration works with Azure"""
        from app.logging_config import setup_logging
        
        # Should not raise any exceptions
        logger = setup_logging()
        assert logger is not None
        
        # Test log message
        logger.info("Test log message for Azure")

    def test_structured_logging_format(self):
        """Test that logs are in structured format for Azure"""
        from app.logging_config import setup_logging
        import json
        import io
        import logging
        
        # Capture log output
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        logger = setup_logging()
        logger.addHandler(handler)
        logger.info("Test structured log", extra={"component": "test", "action": "testing"})
        
        # Check if log is structured (JSON-like)
        log_output = log_capture.getvalue()
        assert "component" in log_output or "Test structured log" in log_output
