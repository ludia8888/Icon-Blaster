#!/usr/bin/env node

const scanner = require('sonarqube-scanner').default;
const path = require('path');

// Load environment variables
require('dotenv').config();

const serverUrl = process.env.SONAR_HOST_URL || 'http://localhost:9000';
const token = process.env.SONAR_TOKEN;

if (!token) {
  console.error('❌ SONAR_TOKEN is not set in environment variables');
  console.error('   Please set it in your .env file or export it');
  process.exit(1);
}

console.log('🚀 Starting SonarQube analysis...');
console.log(`   Server: ${serverUrl}`);
console.log(`   Project: arrakis-project`);

scanner(
  {
    serverUrl,
    token,
    options: {
      'sonar.login': token,
      // sonar-project.properties 파일의 설정을 사용하도록 최소한의 옵션만 제공
      'sonar.projectKey': 'Arrakis-Project',
    },
  },
  () => {
    console.log('✅ SonarQube analysis completed');
    console.log(`📊 View results at: ${serverUrl}/dashboard?id=Arrakis-Project`);
  },
  (error) => {
    console.error('❌ SonarQube analysis failed:', error);
    process.exit(1);
  }
);