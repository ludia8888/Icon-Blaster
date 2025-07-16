# SPICE System Deployment Guide

## 🚀 Production Deployment Guide

### Prerequisites

1. **Docker & Docker Compose**
   ```bash
   # Install Docker
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   
   # Install Docker Compose
   sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
   sudo chmod +x /usr/local/bin/docker-compose
   ```

2. **System Requirements**
   - CPU: 2+ cores
   - RAM: 4GB minimum (8GB recommended)
   - Storage: 20GB+ available
   - OS: Linux (Ubuntu 20.04+ recommended)

### Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd SPICE\ HARVESTER/backend
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your production values
   ```

3. **Deploy the system**
   ```bash
   ./deploy.sh deploy
   ```

### Deployment Commands

```bash
# Build and start all services
./deploy.sh up

# Start services (without building)
./deploy.sh start

# Stop all services
./deploy.sh stop

# View logs
./deploy.sh logs

# Run tests
./deploy.sh test

# Clean everything (including data)
./deploy.sh clean
```

### Service Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│      BFF        │────▶│      OMS        │
│   (Port 3000)   │     │   (Port 8002)   │     │   (Port 8000)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
                                                  ┌─────────────────┐
                                                  │   TerminusDB    │
                                                  │   (Port 6363)   │
                                                  └─────────────────┘
```

### Health Checks

All services include health check endpoints:

- **BFF**: http://localhost:8002/health
- **OMS**: http://localhost:8000/health
- **TerminusDB**: http://localhost:6363/api/

### Monitoring

1. **Check service status**
   ```bash
   docker-compose ps
   ```

2. **View real-time logs**
   ```bash
   docker-compose logs -f [service-name]
   ```

3. **Resource usage**
   ```bash
   docker stats
   ```

### Backup & Recovery

1. **Backup data**
   ```bash
   # Backup TerminusDB data
   docker run --rm -v spice_terminusdb_data:/data -v $(pwd):/backup alpine tar czf /backup/terminusdb-backup-$(date +%Y%m%d).tar.gz -C /data .
   
   # Backup BFF data (Label mappings)
   docker run --rm -v spice_bff_data:/data -v $(pwd):/backup alpine tar czf /backup/bff-backup-$(date +%Y%m%d).tar.gz -C /data .
   ```

2. **Restore data**
   ```bash
   # Restore TerminusDB data
   docker run --rm -v spice_terminusdb_data:/data -v $(pwd):/backup alpine tar xzf /backup/terminusdb-backup-YYYYMMDD.tar.gz -C /data
   
   # Restore BFF data
   docker run --rm -v spice_bff_data:/data -v $(pwd):/backup alpine tar xzf /backup/bff-backup-YYYYMMDD.tar.gz -C /data
   ```

### SSL/TLS Configuration

For production, use a reverse proxy (nginx) with SSL:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /api/bff/ {
        proxy_pass http://localhost:8002/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /api/oms/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Security Best Practices

1. **Change default passwords**
   - Update TERMINUS_KEY in .env
   - Use strong SECRET_KEY

2. **Network isolation**
   - Use Docker networks
   - Expose only necessary ports

3. **Regular updates**
   ```bash
   docker-compose pull
   ./deploy.sh up
   ```

4. **Enable firewall**
   ```bash
   sudo ufw allow 22/tcp
   sudo ufw allow 443/tcp
   sudo ufw enable
   ```

### Troubleshooting

1. **Service won't start**
   ```bash
   # Check logs
   docker-compose logs [service-name]
   
   # Check port conflicts
   sudo lsof -i :8000
   sudo lsof -i :8002
   sudo lsof -i :6363
   ```

2. **Performance issues**
   ```bash
   # Increase Docker resources
   # Edit /etc/docker/daemon.json
   {
     "default-ulimits": {
       "nofile": {
         "Name": "nofile",
         "Hard": 64000,
         "Soft": 64000
       }
     }
   }
   ```

3. **Database connection errors**
   - Ensure TerminusDB is healthy
   - Check network connectivity
   - Verify credentials

### Production Checklist

- [ ] Environment variables configured
- [ ] SSL certificates installed
- [ ] Firewall rules configured
- [ ] Backup strategy in place
- [ ] Monitoring alerts set up
- [ ] Resource limits configured
- [ ] Log rotation enabled
- [ ] Security updates scheduled

### Support

For issues:
1. Check service logs
2. Review health endpoints
3. Consult error messages
4. Open GitHub issue with details

---

## 🎉 Congratulations!

Your SPICE system is now production-ready with:
- ✅ High availability
- ✅ Automatic health checks
- ✅ Data persistence
- ✅ Easy scaling
- ✅ Comprehensive logging
- ✅ Security best practices