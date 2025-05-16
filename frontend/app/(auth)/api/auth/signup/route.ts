import { NextRequest, NextResponse } from 'next/server';

/**
 * Handle signup requests and forward them to the backend API
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
    
    // Forward the signup request to our backend
    // Backend expects username, not email
    const response = await fetch(`${getApiBaseUrl()}/auth/signup`, {
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
        { error: data.detail || 'Registration failed' },
        { status: response.status }
      );
    }
    
    // Return the successful response with tokens
    return NextResponse.json(data);
  } catch (error) {
    console.error('Registration error:', error);
    return NextResponse.json(
      { error: 'Registration failed due to a server error' },
      { status: 500 }
    );
  }
} 