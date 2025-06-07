module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint', 'import', 'jest'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:@typescript-eslint/recommended-requiring-type-checking',
    'prettier'
  ],
  parserOptions: {
    project: ['./tsconfig.json', './packages/*/tsconfig.json']
  },
  rules: {
    // Claude Rules 준수: 함수 크기 제한
    'max-lines-per-function': ['error', { 
      max: 30,
      skipBlankLines: true,
      skipComments: true
    }],
    'complexity': ['error', { max: 10 }],
    
    // TypeScript strict rules
    '@typescript-eslint/strict-boolean-expressions': 'error',
    '@typescript-eslint/no-explicit-any': 'error',
    '@typescript-eslint/explicit-function-return-type': 'error',
    '@typescript-eslint/no-unused-vars': ['error', { 
      argsIgnorePattern: '^_',
      varsIgnorePattern: '^_'
    }],
    
    // Import rules
    'import/order': ['error', {
      'groups': ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
      'newlines-between': 'always',
      'alphabetize': { order: 'asc', caseInsensitive: true }
    }],
    'import/no-duplicates': 'error',
    
    // General best practices
    'no-console': ['warn', { allow: ['warn', 'error'] }],
    'prefer-const': 'error',
    'no-var': 'error',
    'object-shorthand': 'error',
    'prefer-template': 'error'
  },
  overrides: [
    {
      files: ['**/*.test.ts', '**/*.spec.ts'],
      env: {
        jest: true
      },
      rules: {
        'max-lines-per-function': 'off'
      }
    }
  ],
  ignorePatterns: ['dist', 'node_modules', 'coverage', '*.js']
};