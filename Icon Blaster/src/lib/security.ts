// Security utilities for Icon Blaster

export function sanitizePrompt(prompt: string): string {
  if (!prompt || typeof prompt !== 'string') {
    throw new Error('Invalid prompt');
  }

  // Remove potentially dangerous characters
  const cleaned = prompt
    .replace(/[<>\"'`]/g, '') // Remove HTML/script chars
    .replace(/\b(javascript|data|vbscript):/gi, '') // Remove protocol injections
    .replace(/[{}]/g, '') // Remove template injection chars
    .trim();
  
  // Length validation
  if (cleaned.length > 500) {
    throw new Error('Prompt too long (max 500 characters)');
  }
  
  if (cleaned.length < 3) {
    throw new Error('Prompt too short (min 3 characters)');
  }

  // Basic content filtering
  const forbiddenPatterns = [
    /\b(hack|exploit|inject|malware)\b/i,
    /\b(nude|nsfw|sexual|violent)\b/i,
    /<script/i,
    /javascript:/i
  ];

  for (const pattern of forbiddenPatterns) {
    if (pattern.test(cleaned)) {
      throw new Error('Invalid prompt content');
    }
  }
  
  return cleaned;
}

export function validateImageUrl(url: string): boolean {
  try {
    const urlObj = new URL(url);
    const allowedHosts = [
      'oaidalleapiprodscus.blob.core.windows.net',
      'via.placeholder.com'
    ];
    
    return allowedHosts.includes(urlObj.hostname);
  } catch {
    return false;
  }
}

export function validateApiKey(key: string): boolean {
  return key.startsWith('sk-') && key.length >= 51;
}

// Simple in-memory rate limiter (for development)
const requestCounts = new Map<string, { count: number; resetTime: number }>();

export function checkRateLimit(ip: string, maxRequests = 10, windowMs = 60000): boolean {
  const now = Date.now();
  const userRequests = requestCounts.get(ip);
  
  if (!userRequests || now > userRequests.resetTime) {
    requestCounts.set(ip, { count: 1, resetTime: now + windowMs });
    return true;
  }
  
  if (userRequests.count >= maxRequests) {
    return false;
  }
  
  userRequests.count++;
  return true;
}