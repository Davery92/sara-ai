import { NextRequest, NextResponse } from 'next/server';

/**
 * Handle login requests and forward them to the backend API
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
      // Return the error from the backend with the appropriate status code
      return NextResponse.json(
        { error: data.detail || 'Authentication failed' },
        { status: response.status }
      );
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
    console.error('Login error:', error);
    return NextResponse.json(
      { error: 'Authentication failed due to a server error' },
      { status: 500 }
    );
  }
} 