#!/bin/bash

# SonarQube Local Setup Script

set -e

echo "🚀 Setting up SonarQube for Arrakis Project..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Start SonarQube
echo -e "${YELLOW}Starting SonarQube containers...${NC}"
docker-compose -f docker-compose.sonarqube.yml up -d

# Wait for SonarQube to be ready
echo -e "${YELLOW}Waiting for SonarQube to start (this may take a few minutes)...${NC}"
until curl -s http://localhost:9000/api/system/status | grep -q '"status":"UP"'; do
    echo -n "."
    sleep 5
done
echo ""

echo -e "${GREEN}✅ SonarQube is running!${NC}"
echo ""
echo "📊 Access SonarQube at: http://localhost:9000"
echo "   Default credentials: admin/admin"
echo ""
echo "🔧 To configure your project:"
echo "   1. Log in to SonarQube"
echo "   2. Create a new project with key: arrakis-project"
echo "   3. Generate a token and save it"
echo "   4. Run analysis with: npm run sonar"
echo ""
echo "💡 Tips:"
echo "   - Stop SonarQube: npm run sonar:stop"
echo "   - View logs: docker-compose -f docker-compose.sonarqube.yml logs"
echo ""

# Create .env.example if it doesn't exist
if [ ! -f .env.example ]; then
    echo -e "${YELLOW}Creating .env.example file...${NC}"
    cat > .env.example << EOF
# SonarQube Configuration
SONAR_HOST_URL=http://localhost:9000
SONAR_TOKEN=your_token_here
SONAR_PROJECT_KEY=arrakis-project
EOF
    echo -e "${GREEN}✅ Created .env.example${NC}"
fi

# Check if sonar-scanner is installed
if ! command -v sonar-scanner &> /dev/null; then
    echo -e "${YELLOW}⚠️  sonar-scanner is not installed globally.${NC}"
    echo "   Install it with: npm install -g sonarqube-scanner"
    echo "   Or use Docker: docker run --rm -v \$(pwd):/usr/src sonarsource/sonar-scanner-cli"
fi

echo -e "${GREEN}✅ Setup complete!${NC}"