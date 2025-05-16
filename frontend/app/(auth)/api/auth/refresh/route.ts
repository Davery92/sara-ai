import { NextRequest, NextResponse } from 'next/server';

/**
 * Handle token refresh requests and forward them to the backend API
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
    // Try to get refresh token from the request body
    let refresh_token;
    
    try {
      const body = await request.json();
      refresh_token = body.refresh_token;
    } catch (e) {
      // If parsing request body fails, try getting token from cookie
      refresh_token = request.cookies.get('refreshToken')?.value;
    }
    
    if (!refresh_token) {
      return NextResponse.json({ error: 'Refresh token is required' }, { status: 400 });
    }
    
    // Forward the refresh request to our backend
    const response = await fetch(`${getApiBaseUrl()}/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token }),
    });
    
    const data = await response.json();
    
    if (!response.ok) {
      // Return the error from the backend with the appropriate status code
      return NextResponse.json(
        { error: data.detail || 'Token refresh failed' },
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
    console.error('Token refresh error:', error);
    return NextResponse.json(
      { error: 'Token refresh failed due to a server error' },
      { status: 500 }
    );
  }
} 