// Environment Configuration for Icon Blaster
// Handles development vs production environment differences

export interface AppConfig {
  // Environment
  nodeEnv: string;
  isDevelopment: boolean;
  isProduction: boolean;
  
  // Server
  port: number;
  appUrl: string;
  
  // Application
  debugMode: boolean;
  mockApi: boolean;
  
  // Rate Limiting
  rateLimitMax: number;
  rateLimitWindowMs: number;
  
  // Security
  securityStrictMode: boolean;
  corsOrigins: string[];
  
  // APIs
  openaiApiKey: string;
}

function getEnvVar(key: string, defaultValue?: string): string {
  const value = process.env[key];
  if (!value && defaultValue === undefined) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value || defaultValue || '';
}

function getEnvNumber(key: string, defaultValue: number): number {
  const value = process.env[key];
  return value ? parseInt(value, 10) : defaultValue;
}

function getEnvBoolean(key: string, defaultValue: boolean): boolean {
  const value = process.env[key];
  if (!value) return defaultValue;
  return value.toLowerCase() === 'true';
}

export function getConfig(): AppConfig {
  const nodeEnv = getEnvVar('NODE_ENV', 'development');
  const isDevelopment = nodeEnv === 'development';
  const isProduction = nodeEnv === 'production';
  
  return {
    // Environment
    nodeEnv,
    isDevelopment,
    isProduction,
    
    // Server
    port: getEnvNumber('PORT', isDevelopment ? 3002 : 3000),
    appUrl: getEnvVar('NEXT_PUBLIC_APP_URL', 'http://localhost:3002'),
    
    // Application
    debugMode: getEnvBoolean('NEXT_PUBLIC_DEBUG_MODE', isDevelopment),
    mockApi: getEnvBoolean('NEXT_PUBLIC_MOCK_API', false),
    
    // Rate Limiting
    rateLimitMax: getEnvNumber('RATE_LIMIT_MAX', isDevelopment ? 50 : 10),
    rateLimitWindowMs: getEnvNumber('RATE_LIMIT_WINDOW_MS', 60000),
    
    // Security
    securityStrictMode: getEnvBoolean('SECURITY_STRICT_MODE', isProduction),
    corsOrigins: getEnvVar('CORS_ORIGINS', '').split(',').filter(Boolean),
    
    // APIs
    openaiApiKey: getEnvVar('OPENAI_API_KEY'),
  };
}

// Singleton config instance
let config: AppConfig | null = null;

export function useConfig(): AppConfig {
  if (!config) {
    config = getConfig();
  }
  return config;
}

// Development utilities
export function logConfig(): void {
  const cfg = useConfig();
  if (cfg.debugMode) {
    console.log('🔧 Icon Blaster Configuration:', {
      environment: cfg.nodeEnv,
      port: cfg.port,
      appUrl: cfg.appUrl,
      debugMode: cfg.debugMode,
      rateLimitMax: cfg.rateLimitMax,
      securityStrictMode: cfg.securityStrictMode,
    });
  }
}