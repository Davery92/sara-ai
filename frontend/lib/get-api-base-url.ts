export const getApiBaseUrl = (context: 'client' | 'server'): string => {
  if (context === 'server') {
    // For server-side fetches (within Docker or local Node.js)
    // This should be the base URL of the gateway service, e.g., http://gateway:8000
    return process.env.INTERNAL_BACKEND_API_URL || 'http://gateway:8000';
  } else {
    // For client-side (browser) fetches
    // This should be the publicly accessible base URL of the gateway, e.g., http://localhost:8000
    return process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';
  }
}; 