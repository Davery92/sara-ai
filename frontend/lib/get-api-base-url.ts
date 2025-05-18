export const getApiBaseUrl = (context: 'client' | 'server'): string => {
  if (context === 'server') {
    // For server-side fetches (within Docker or local Node.js)
    const internalUrl = process.env.INTERNAL_BACKEND_API_URL;
    if (internalUrl) {
      // Remove trailing /v1 if present
      return internalUrl.replace(/\/v1$/, '');
    }
    // Fallback for local server-side development
    return 'http://localhost:8000';
  } else {
    // For client-side (browser) fetches
    const publicApiUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || '/v1';
    return publicApiUrl;
  }
}; 