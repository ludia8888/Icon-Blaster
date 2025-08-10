// Environment variable validation
import { validateApiKey } from './security';

export function validateEnvironment() {
  const requiredVars = {
    OPENAI_API_KEY: process.env.OPENAI_API_KEY,
  };

  const missing: string[] = [];
  const invalid: string[] = [];

  for (const [key, value] of Object.entries(requiredVars)) {
    if (!value) {
      missing.push(key);
      continue;
    }

    // Specific validations
    if (key === 'OPENAI_API_KEY' && !validateApiKey(value)) {
      invalid.push(key);
    }
  }

  if (missing.length > 0) {
    throw new Error(`Missing required environment variables: ${missing.join(', ')}`);
  }

  if (invalid.length > 0) {
    throw new Error(`Invalid environment variables: ${invalid.join(', ')}`);
  }
}

// Validate on import (fail fast) - only in production
if (process.env.NODE_ENV === 'production') {
  try {
    validateEnvironment();
  } catch (error) {
    console.error('Environment validation failed:', error);
    process.exit(1);
  }
}