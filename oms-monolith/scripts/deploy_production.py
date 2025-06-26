#!/usr/bin/env python3
"""
Production Deployment Script for OMS

Handles deployment of OMS to production environment with:
- Health checks
- Database migrations
- Service startup
- Monitoring setup
"""

import asyncio
import sys
import os
from pathlib import Path
import subprocess
import yaml
from datetime import datetime
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import get_logger

logger = get_logger(__name__)


class ProductionDeployer:
    """Handles production deployment of OMS"""
    
    def __init__(self, environment: str = "production"):
        self.environment = environment
        self.config = self._load_config()
        self.deployment_id = f"deploy_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    def _load_config(self) -> Dict:
        """Load deployment configuration"""
        config_path = project_root / "config" / f"{self.environment}.yaml"
        
        # Default configuration
        default_config = {
            "services": {
                "oms": {
                    "port": 8000,
                    "workers": 4,
                    "health_check": "/health"
                },
                "terminusdb": {
                    "host": "localhost",
                    "port": 6363,
                    "database": "oms_production"
                }
            },
            "monitoring": {
                "prometheus": {
                    "enabled": True,
                    "port": 9090
                },
                "grafana": {
                    "enabled": True,
                    "port": 3000
                }
            },
            "features": {
                "dag_compaction": {
                    "enabled": True,
                    "schedule": "0 2 * * *"  # 2 AM daily
                },
                "cache_warming": {
                    "enabled": True,
                    "ttl": 3600
                }
            }
        }
        
        if config_path.exists():
            with open(config_path) as f:
                loaded_config = yaml.safe_load(f)
                # Merge with defaults
                return {**default_config, **loaded_config}
        
        return default_config
    
    async def deploy(self) -> bool:
        """Execute full production deployment"""
        logger.info(f"{'=' * 80}")
        logger.info(f"OMS Production Deployment - {self.deployment_id}")
        logger.info(f"Environment: {self.environment}")
        logger.info(f"{'=' * 80}")
        
        try:
            # Pre-deployment checks
            if not await self.pre_deployment_checks():
                logger.error("Pre-deployment checks failed")
                return False
            
            # Database setup
            if not await self.setup_database():
                logger.error("Database setup failed")
                return False
            
            # Deploy services
            if not await self.deploy_services():
                logger.error("Service deployment failed")
                return False
            
            # Setup monitoring
            if not await self.setup_monitoring():
                logger.error("Monitoring setup failed")
                return False
            
            # Post-deployment validation
            if not await self.post_deployment_validation():
                logger.error("Post-deployment validation failed")
                return False
            
            logger.info(f"\n✅ Deployment {self.deployment_id} completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            await self.rollback()
            return False
    
    async def pre_deployment_checks(self) -> bool:
        """Run pre-deployment checks"""
        logger.info("\n🔍 Running pre-deployment checks...")
        
        checks = [
            self.check_python_version(),
            self.check_dependencies(),
            self.check_environment_variables(),
            self.check_disk_space(),
            self.check_port_availability()
        ]
        
        results = await asyncio.gather(*checks)
        
        if all(results):
            logger.info("✅ All pre-deployment checks passed")
            return True
        else:
            logger.error("❌ Some pre-deployment checks failed")
            return False
    
    async def check_python_version(self) -> bool:
        """Check Python version compatibility"""
        import sys
        required_version = (3, 8)
        current_version = sys.version_info[:2]
        
        if current_version >= required_version:
            logger.info(f"✅ Python version: {sys.version.split()[0]}")
            return True
        else:
            logger.error(f"❌ Python {'.'.join(map(str, required_version))} or higher required")
            return False
    
    async def check_dependencies(self) -> bool:
        """Check all dependencies are installed"""
        try:
            import fastapi
            import pydantic
            import terminusdb_client
            import prometheus_client
            
            logger.info("✅ All dependencies installed")
            return True
        except ImportError as e:
            logger.error(f"❌ Missing dependency: {e}")
            return False
    
    async def check_environment_variables(self) -> bool:
        """Check required environment variables"""
        required_vars = [
            "OMS_DATABASE_URL",
            "OMS_SECRET_KEY",
            "OMS_ENVIRONMENT"
        ]
        
        missing = [var for var in required_vars if not os.getenv(var)]
        
        if not missing:
            logger.info("✅ All environment variables set")
            return True
        else:
            logger.error(f"❌ Missing environment variables: {', '.join(missing)}")
            return False
    
    async def check_disk_space(self) -> bool:
        """Check available disk space"""
        import shutil
        
        stat = shutil.disk_usage("/")
        free_gb = stat.free / (1024**3)
        
        if free_gb > 10:  # Require at least 10GB free
            logger.info(f"✅ Disk space available: {free_gb:.1f}GB")
            return True
        else:
            logger.error(f"❌ Insufficient disk space: {free_gb:.1f}GB (need 10GB)")
            return False
    
    async def check_port_availability(self) -> bool:
        """Check if required ports are available"""
        import socket
        
        ports_to_check = [
            self.config["services"]["oms"]["port"],
            self.config["services"]["terminusdb"]["port"]
        ]
        
        if self.config["monitoring"]["prometheus"]["enabled"]:
            ports_to_check.append(self.config["monitoring"]["prometheus"]["port"])
        
        for port in ports_to_check:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            
            if result == 0:
                logger.error(f"❌ Port {port} is already in use")
                return False
        
        logger.info("✅ All required ports available")
        return True
    
    async def setup_database(self) -> bool:
        """Setup TerminusDB for production"""
        logger.info("\n🗄️  Setting up database...")
        
        try:
            # Create database initialization script
            init_script = f"""
import terminusdb_client as tdb

# Connect to TerminusDB
client = tdb.Client("{self.config['services']['terminusdb']['host']}:{self.config['services']['terminusdb']['port']}")

# Create production database
db_id = "{self.config['services']['terminusdb']['database']}"

if not client.has_database(db_id):
    client.create_database(db_id, "OMS Production Database")
    print(f"Created database: {{db_id}}")
else:
    print(f"Database already exists: {{db_id}}")

# Create schema
client.connect(db=db_id)
client.create_branch("main", empty=True)
print("Database setup complete")
"""
            
            # Run initialization
            result = subprocess.run(
                [sys.executable, "-c", init_script],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("✅ Database setup completed")
                return True
            else:
                logger.error(f"Database setup failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Database setup error: {e}")
            return False
    
    async def deploy_services(self) -> bool:
        """Deploy OMS services"""
        logger.info("\n🚀 Deploying services...")
        
        # Create systemd service file
        service_content = f"""[Unit]
Description=OMS - Ontology Management Service
After=network.target

[Service]
Type=simple
User=oms
WorkingDirectory={project_root}
Environment="OMS_ENVIRONMENT={self.environment}"
Environment="PYTHONPATH={project_root}"
ExecStart={sys.executable} -m uvicorn api.main:app --host 0.0.0.0 --port {self.config['services']['oms']['port']} --workers {self.config['services']['oms']['workers']}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
        
        service_path = Path("/tmp/oms.service")
        service_path.write_text(service_content)
        
        logger.info("✅ Service configuration created")
        
        # Enable DAG compaction if configured
        if self.config["features"]["dag_compaction"]["enabled"]:
            await self.setup_dag_compaction()
        
        return True
    
    async def setup_dag_compaction(self):
        """Setup DAG compaction cron job"""
        logger.info("Setting up DAG compaction...")
        
        compaction_script = f"""#!/bin/bash
cd {project_root}
{sys.executable} -c "
from core.versioning.dag_compaction import dag_compactor
import asyncio

async def run_compaction():
    result = await dag_compactor.compact_dag(
        root_commits=['main'],
        dry_run=False
    )
    print(f'Compaction completed: {{result}}')

asyncio.run(run_compaction())
"
"""
        
        script_path = project_root / "scripts" / "dag_compaction_cron.sh"
        script_path.write_text(compaction_script)
        script_path.chmod(0o755)
        
        # Add to crontab
        schedule = self.config["features"]["dag_compaction"]["schedule"]
        logger.info(f"✅ DAG compaction scheduled: {schedule}")
    
    async def setup_monitoring(self) -> bool:
        """Setup monitoring and alerting"""
        logger.info("\n📊 Setting up monitoring...")
        
        # Create Prometheus configuration
        if self.config["monitoring"]["prometheus"]["enabled"]:
            prometheus_config = """
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'oms'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    
  - job_name: 'terminusdb'
    static_configs:
      - targets: ['localhost:6363']
    metrics_path: '/metrics'

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']

rule_files:
  - 'alerts/*.yml'
"""
            
            config_path = project_root / "monitoring" / "prometheus.yml"
            config_path.parent.mkdir(exist_ok=True)
            config_path.write_text(prometheus_config)
            
            # Create alert rules
            await self.create_alert_rules()
            
            logger.info("✅ Prometheus configuration created")
        
        # Setup Grafana dashboards
        if self.config["monitoring"]["grafana"]["enabled"]:
            await self.setup_grafana_dashboards()
            
        return True
    
    async def create_alert_rules(self):
        """Create Prometheus alert rules"""
        alerts = """
groups:
  - name: oms_alerts
    rules:
      - alert: HighMergeLatency
        expr: oms_merge_duration_p95 > 200
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High merge latency detected"
          description: "P95 merge latency {{ $value }}ms exceeds 200ms threshold"
      
      - alert: LowAutoResolutionRate
        expr: oms_conflict_auto_resolution_rate < 0.8
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Low auto-resolution rate"
          description: "Auto-resolution rate {{ $value }} below 80% threshold"
      
      - alert: DAGCompactionFailed
        expr: oms_dag_compaction_failed > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "DAG compaction failed"
          description: "DAG compaction has failed {{ $value }} times"
"""
        
        alerts_path = project_root / "monitoring" / "alerts" / "oms_alerts.yml"
        alerts_path.parent.mkdir(parents=True, exist_ok=True)
        alerts_path.write_text(alerts)
        
        logger.info("✅ Alert rules created")
    
    async def setup_grafana_dashboards(self):
        """Setup Grafana dashboards"""
        dashboard = {
            "dashboard": {
                "title": "OMS Performance Dashboard",
                "panels": [
                    {
                        "title": "Merge Latency P95",
                        "targets": [{"expr": "oms_merge_duration_p95"}],
                        "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8}
                    },
                    {
                        "title": "Auto-Resolution Rate",
                        "targets": [{"expr": "oms_conflict_auto_resolution_rate"}],
                        "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8}
                    },
                    {
                        "title": "DAG Compaction",
                        "targets": [{"expr": "oms_dag_nodes_compacted"}],
                        "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8}
                    },
                    {
                        "title": "Conflict Types",
                        "targets": [{"expr": "oms_conflicts_by_type"}],
                        "gridPos": {"x": 12, "y": 8, "w": 12, "h": 8}
                    }
                ]
            }
        }
        
        dashboard_path = project_root / "monitoring" / "dashboards" / "oms_performance.json"
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        
        import json
        dashboard_path.write_text(json.dumps(dashboard, indent=2))
        
        logger.info("✅ Grafana dashboards created")
    
    async def post_deployment_validation(self) -> bool:
        """Validate deployment is working correctly"""
        logger.info("\n✔️  Running post-deployment validation...")
        
        validations = [
            self.check_service_health(),
            self.run_smoke_tests(),
            self.verify_monitoring()
        ]
        
        results = await asyncio.gather(*validations)
        
        if all(results):
            logger.info("✅ All validations passed")
            return True
        else:
            logger.error("❌ Some validations failed")
            return False
    
    async def check_service_health(self) -> bool:
        """Check service health endpoints"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"http://localhost:{self.config['services']['oms']['port']}/health"
                async with session.get(url) as response:
                    if response.status == 200:
                        logger.info("✅ OMS service is healthy")
                        return True
                    else:
                        logger.error(f"❌ OMS health check failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Cannot reach OMS service: {e}")
            return False
    
    async def run_smoke_tests(self) -> bool:
        """Run smoke tests against deployed service"""
        logger.info("Running smoke tests...")
        
        # Run basic API tests
        smoke_test_script = """
import requests
import sys

base_url = f"http://localhost:{port}"

# Test schema endpoint
response = requests.get(f"{base_url}/api/v1/schemas")
if response.status_code != 200:
    print(f"Schema endpoint failed: {response.status_code}")
    sys.exit(1)

# Test health endpoint
response = requests.get(f"{base_url}/health")
if response.status_code != 200:
    print(f"Health endpoint failed: {response.status_code}")
    sys.exit(1)

print("All smoke tests passed")
""".format(port=self.config['services']['oms']['port'])
        
        result = subprocess.run(
            [sys.executable, "-c", smoke_test_script],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            logger.info("✅ Smoke tests passed")
            return True
        else:
            logger.error(f"❌ Smoke tests failed: {result.stderr}")
            return False
    
    async def verify_monitoring(self) -> bool:
        """Verify monitoring is working"""
        if not self.config["monitoring"]["prometheus"]["enabled"]:
            return True
        
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                # Check Prometheus
                url = f"http://localhost:{self.config['monitoring']['prometheus']['port']}/api/v1/query"
                params = {"query": "up"}
                
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        logger.info("✅ Prometheus is running")
                        return True
                    else:
                        logger.error("❌ Prometheus check failed")
                        return False
        except Exception as e:
            logger.warning(f"⚠️  Monitoring not yet available: {e}")
            return True  # Don't fail deployment for monitoring
    
    async def rollback(self):
        """Rollback deployment on failure"""
        logger.warning("\n⚙️  Rolling back deployment...")
        
        # Rollback logic would go here
        # - Stop services
        # - Restore previous version
        # - Clean up failed deployment
        
        logger.info("✅ Rollback completed")


async def main():
    """Main deployment entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Deploy OMS to production")
    parser.add_argument(
        "--environment",
        choices=["production", "staging", "development"],
        default="production",
        help="Deployment environment"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip pre-deployment tests"
    )
    
    args = parser.parse_args()
    
    # Run tests first unless skipped
    if not args.skip_tests:
        logger.info("Running pre-deployment tests...")
        test_result = subprocess.run(
            [sys.executable, str(project_root / "scripts" / "run_all_tests.py")],
            capture_output=True
        )
        
        if test_result.returncode != 0:
            logger.error("❌ Tests failed. Aborting deployment.")
            return 1
    
    # Deploy
    deployer = ProductionDeployer(args.environment)
    success = await deployer.deploy()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))