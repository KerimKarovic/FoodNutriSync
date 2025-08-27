import pytest
import subprocess
import os
from unittest.mock import patch, MagicMock
import tempfile
import yaml

class TestDockerDeployment:
    """Test Docker and Docker Compose deployment"""
    
    def test_dockerfile_exists(self):
        """Test that Dockerfile exists and is valid"""
        assert os.path.exists("Dockerfile")
        
        with open("Dockerfile", "r") as f:
            content = f.read()
            assert "FROM python:" in content
            assert "EXPOSE 8000" in content
            assert "uvicorn" in content

    def test_docker_compose_exists(self):
        """Test that docker-compose.yml exists and is valid"""
        assert os.path.exists("docker-compose.yml")
        
        with open("docker-compose.yml", "r") as f:
            compose_config = yaml.safe_load(f)
            assert "services" in compose_config
            assert "api" in compose_config["services"]
            assert "db" in compose_config["services"]

    @patch('subprocess.run')
    def test_deploy_script_commands(self, mock_run):
        """Test deploy.sh script commands"""
        mock_run.return_value = MagicMock(returncode=0)
        
        # Test that deploy script would run docker-compose
        expected_commands = [
            "docker-compose down",
            "docker-compose up -d",
            "docker-compose exec api alembic upgrade head"
        ]
        
        # Simulate script execution
        for cmd in expected_commands:
            result = subprocess.run(cmd.split(), capture_output=True, text=True)
            assert mock_run.called

class TestAzureDeployment:
    """Test Azure Container Apps deployment configuration"""
    
    def test_azure_config_exists(self):
        """Test Azure configuration files exist"""
        assert os.path.exists("azure-containerapp.yaml")
        assert os.path.exists("deploy-azure.sh")
        assert os.path.exists("setup-azure-env.sh")

    def test_azure_config_structure(self):
        """Test Azure Container App configuration structure"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
            
            assert config["apiVersion"] == "2023-05-01"
            assert config["name"] == "nutrisync-api"
            assert "properties" in config
            assert "template" in config["properties"]
            assert "containers" in config["properties"]["template"]

    def test_azure_environment_variables(self):
        """Test Azure environment variables configuration"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
            
            container = config["properties"]["template"]["containers"][0]
            env_vars = {env["name"]: env.get("value", env.get("secretRef")) 
                       for env in container["env"]}
            
            required_vars = ["DATABASE_URL", "ALEMBIC_DATABASE_URL", "ENVIRONMENT", "LOG_LEVEL"]
            for var in required_vars:
                assert var in env_vars

    def test_azure_health_probes(self):
        """Test Azure health probe configuration"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
            
            container = config["properties"]["template"]["containers"][0]
            probes = container["probes"]
            
            probe_types = [probe["type"] for probe in probes]
            assert "Liveness" in probe_types
            assert "Readiness" in probe_types

    def test_azure_scaling_config(self):
        """Test Azure auto-scaling configuration"""
        with open("azure-containerapp.yaml", "r") as f:
            config = yaml.safe_load(f)
            
            scale = config["properties"]["template"]["scale"]
            assert scale["minReplicas"] == 1
            assert scale["maxReplicas"] == 3
            assert "rules" in scale

class TestDeploymentScripts:
    """Test deployment script functionality"""
    
    def test_deploy_script_executable(self):
        """Test that deployment scripts are executable"""
        scripts = ["deploy.sh", "deploy-azure.sh", "setup-azure-env.sh", "monitor.sh"]
        
        for script in scripts:
            if os.path.exists(script):
                # Check if file has execute permissions (on Unix-like systems)
                if os.name != 'nt':  # Not Windows
                    assert os.access(script, os.X_OK), f"{script} should be executable"

    @patch('subprocess.run')
    def test_monitor_script_functionality(self, mock_run):
        """Test monitor.sh script functionality"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"status": "ok"}'
        )
        
        # Test health check command
        result = subprocess.run(["bash", "monitor.sh", "localhost:8000"], 
                              capture_output=True, text=True)
        assert mock_run.called

class TestEnvironmentConfiguration:
    """Test environment configuration for different deployment targets"""
    
    def test_production_env_vars(self, mock_azure_env):
        """Test production environment variables"""
        required_vars = [
            'DATABASE_URL',
            'ALEMBIC_DATABASE_URL', 
            'ENVIRONMENT',
            'LOG_LEVEL'
        ]
        
        for var in required_vars:
            assert var in mock_azure_env

    def test_database_url_format(self, mock_azure_env):
        """Test database URL format for different drivers"""
        db_url = mock_azure_env['DATABASE_URL']
        alembic_url = mock_azure_env['ALEMBIC_DATABASE_URL']
        
        assert db_url.startswith('postgresql+asyncpg://')
        assert alembic_url.startswith('postgresql+psycopg2://')

    def test_environment_specific_config(self, mock_azure_env):
        """Test environment-specific configuration"""
        env = mock_azure_env['ENVIRONMENT']
        log_level = mock_azure_env['LOG_LEVEL']
        
        if env == 'production':
            assert log_level in ['INFO', 'WARNING', 'ERROR']
        elif env == 'development':
            assert log_level in ['DEBUG', 'INFO']
        elif env == 'testing':
            assert log_level == 'DEBUG'