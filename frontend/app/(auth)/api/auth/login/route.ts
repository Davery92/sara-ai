import { NextRequest, NextResponse } from 'next/server';
import { getApiBaseUrl } from '@/lib/get-api-base-url';

/**
 * Handle login requests and forward them to the backend API
 */

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { email, password } = body;
    
    // Determine backend URL using shared utility
    const serverApiBaseUrl = getApiBaseUrl('server');
    const backendLoginUrl = `${serverApiBaseUrl}/auth/login`;
    console.log(`[API/LOGIN] Calling backend at: ${backendLoginUrl}`);
    
    // Forward the login request to our backend (expects username, not email)
    const backendResponse = await fetch(backendLoginUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username: email, password }),
    });
    
    const responseData = await backendResponse.json();
    
    if (!backendResponse.ok) {
      console.error(`[API/LOGIN] Backend login error (${backendResponse.status}):`, responseData.detail || backendResponse.statusText);
      return NextResponse.json(
        { error: responseData.detail || 'Authentication failed' },
        { status: backendResponse.status }
      );
    }
    
    // Return JSON response for successful login (client will handle navigation)
    const response = NextResponse.json({ success: true });

    // Set cookies with consistent settings
    if (responseData.access_token) {
      console.log('[API/LOGIN] Setting accessToken cookie');
      response.cookies.set({
        name: 'accessToken',
        value: responseData.access_token,
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        maxAge: 60 * 60 * 24 * 7, // 7 days
        path: '/',
      });
    }
    
    if (responseData.refresh_token) {
      console.log('[API/LOGIN] Setting refreshToken cookie');
      response.cookies.set({
        name: 'refreshToken',
        value: responseData.refresh_token,
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'strict',
        maxAge: 60 * 60 * 24 * 30, // 30 days
        path: '/',
      });
    }

    console.log('[API/LOGIN] Returning redirect response with cookies');
    return response;
  } catch (error: any) {
    console.error('[API/LOGIN] Error in login route handler:', error);
    let causeMessage = error.cause?.code || error.message || 'Unknown error';
    return NextResponse.json(
      { error: 'Login proxy failed', details: causeMessage },
      { status: 500 }
    );
  }
} 