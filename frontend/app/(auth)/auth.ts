import { NextRequest, NextResponse } from 'next/server';

/**
 * Handle authentication requests from Next.js
 * This will proxy the requests to our backend authentication service
 */

// Get base API URL from environment
const getApiBaseUrl = () => {
  const baseUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';
  
  // Ensure we don't have a trailing slash that could cause double slashes
  if (baseUrl.endsWith('/')) {
    return baseUrl.slice(0, -1);
  }
  
  return baseUrl;
};

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const callbackUrl = searchParams.get('callbackUrl');
  
  // Redirect to login page with callback URL if provided
  if (callbackUrl) {
    return NextResponse.redirect(new URL(`/login?callbackUrl=${encodeURIComponent(callbackUrl)}`, request.url));
  }
  
  // Otherwise redirect to login page
  return NextResponse.redirect(new URL('/login', request.url));
}

// Auth helper object that can be imported by components
export const auth = {
  // Login the user with tokens
  login: async (accessToken: string, refreshToken: string) => {
    // Store tokens in memory (for client-side components) - This might be redundant with HttpOnly cookies
    if (typeof window !== 'undefined') {
      // localStorage.setItem('accessToken', accessToken); // Consider removing
      // localStorage.setItem('refreshToken', refreshToken); // Consider removing
    }
    return true;
  },
  
  // Logout the user
  logout: async () => {
    // Clear tokens from memory
    if (typeof window !== 'undefined') {
      localStorage.removeItem('accessToken');
      localStorage.removeItem('refreshToken');
    }
    
    // Clear cookies by making a request to the server
    await fetch('/api/auth/logout', { method: 'POST' });
    
    // Redirect to login page
    window.location.href = '/login';
  },
  
  // Check if the user is authenticated
  isAuthenticated: async () => {
    try {
      // Try to get current user profile
      // This relies on the /api/auth/me route which should read cookies
      const response = await fetch('/api/auth/me');
      return response.ok;
    } catch (error) {
      return false;
    }
  }
}; 