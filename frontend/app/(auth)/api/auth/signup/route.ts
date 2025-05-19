import { NextRequest, NextResponse } from 'next/server';
import { getApiBaseUrl } from '@/lib/get-api-base-url';

/**
 * Handle signup requests and forward them to the backend API
 */

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { email, password } = body;
    
    // Determine backend URL using shared utility
    const serverApiBaseUrl = getApiBaseUrl('server');
    const backendSignupUrl = `${serverApiBaseUrl}/auth/signup`;
    console.log(`[API/SIGNUP] Calling backend at: ${backendSignupUrl}`);
    // Forward the signup request to our backend (expects username, not email)
    const backendResponse = await fetch(backendSignupUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username: email, password }),
    });
    
    const responseData = await backendResponse.json();
    
    if (!backendResponse.ok) {
      console.error(`[API/SIGNUP] Backend signup error (${backendResponse.status}):`, responseData.detail || backendResponse.statusText);
      // Return the error from the backend with the appropriate status code
      return NextResponse.json(
        { error: responseData.detail || 'Registration failed' },
        { status: backendResponse.status }
      );
    }
    
    // If signup is successful, set cookies and return success
    const response = NextResponse.json({ success: true });

    if (responseData.access_token) {
      console.log('[API/SIGNUP] Setting accessToken cookie');
      response.cookies.set({
        name: 'accessToken',
        value: responseData.access_token,
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        maxAge: 60 * 60 * 24 * 7,
        path: '/',
      });
    }
    
    if (responseData.refresh_token) {
      console.log('[API/SIGNUP] Setting refreshToken cookie');
      response.cookies.set({
        name: 'refreshToken',
        value: responseData.refresh_token,
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'strict',
        maxAge: 60 * 60 * 24 * 30,
        path: '/',
      });
    }
    
    console.log('[API/SIGNUP] Returning response with cookies.');
    return response;

  } catch (error: any) {
    console.error('[API/SIGNUP] Error in signup route handler:', error);
    let causeMessage = error.cause?.code || error.message || 'Unknown error';
    return NextResponse.json(
      { error: 'Signup proxy failed', details: causeMessage },
      { status: 500 }
    );
  }
} 