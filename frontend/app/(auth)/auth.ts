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

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { email, password } = body;
    
    // Forward the login request to our backend
    // Backend expects username, not email
    const response = await fetch(`${getApiBaseUrl()}/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username: email, password }),
    });
    
    const data = await response.json();
    
    if (!response.ok) {
      // Return the error from the backend
      return NextResponse.json({ error: data.detail || 'Authentication failed' }, { status: response.status });
    }
    
    // Create a new response with tokens
    const responseWithCookies = NextResponse.json(data);
    
    // Set the access token as an HttpOnly cookie
    responseWithCookies.cookies.set({
      name: 'accessToken',
      value: data.access_token,
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      maxAge: 60 * 60 * 24 * 7, // 7 days (matching the extended token lifetime)
      path: '/'
    });
    
    // Also set the refresh token as an HttpOnly cookie
    // This is safer than storing it in localStorage
    responseWithCookies.cookies.set({
      name: 'refreshToken',
      value: data.refresh_token,
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      maxAge: 60 * 60 * 24 * 30, // 30 days
      path: '/'
    });
    
    return responseWithCookies;
  } catch (error) {
    console.error('Authentication error:', error);
    return NextResponse.json({ error: 'Authentication failed' }, { status: 500 });
  }
}

// Auth helper object that can be imported by components
export const auth = {
  // Login the user with tokens
  login: async (accessToken: string, refreshToken: string) => {
    // Store tokens in memory (for client-side components)
    if (typeof window !== 'undefined') {
      localStorage.setItem('accessToken', accessToken);
      localStorage.setItem('refreshToken', refreshToken);
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
      const response = await fetch('/api/auth/me');
      return response.ok;
    } catch (error) {
      return false;
    }
  }
}; 