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
      console.error(`[API/LOGIN] Backend login error (${backendResponse.status}):`, responseData.detail || responseData);
      return NextResponse.json(
        { success: false, error: responseData.detail || 'Authentication failed' },
        { status: backendResponse.status }
      );
    }
    
    // Return JSON response for successful login (client will handle navigation)
    const response = NextResponse.json({ 
      success: true, 
    });

    // Determine if the connection is secure (HTTPS)
    // The `x-forwarded-proto` header is often set by reverse proxies (like Traefik, Nginx)
    // For direct connections, request.nextUrl.protocol is reliable.
    const requestProtocol = request.headers.get('x-forwarded-proto') || request.nextUrl.protocol.replace(':', '');
    const isConnectionSecure = requestProtocol === 'https';
    
    // Cookies should be secure ONLY if the connection is HTTPS.
    // For local development over HTTP, secure MUST be false.
    // We ignore NODE_ENV here for simplicity and rely purely on the connection protocol.
    const cookieSecureFlag = isConnectionSecure;

    console.log(`[API/LOGIN/SIGNUP] Cookie Secure Flag will be: ${cookieSecureFlag} (Protocol: ${requestProtocol}, NODE_ENV: ${process.env.NODE_ENV})`);

    // Set cookies with consistent settings
    if (responseData.access_token) {
      console.log('[API/LOGIN/SIGNUP] Setting accessToken cookie');
      response.cookies.set({
        name: 'accessToken',
        value: responseData.access_token,
        httpOnly: true,
        secure: cookieSecureFlag,
        sameSite: 'lax',
        maxAge: 60 * 60 * 24 * 7, // 7 days
        path: '/',
      });
    }
    
    if (responseData.refresh_token) {
      console.log('[API/LOGIN/SIGNUP] Setting refreshToken cookie');
      response.cookies.set({
        name: 'refreshToken',
        value: responseData.refresh_token,
        httpOnly: true,
        secure: cookieSecureFlag,
        sameSite: 'strict',
        maxAge: 60 * 60 * 24 * 30, // 30 days
        path: '/',
      });
    }

    console.log('[API/LOGIN/SIGNUP] Returning JSON response with cookies set.');
    return response;
  } catch (error: any) {
    console.error('[API/LOGIN] Error in login route handler:', error);
    let causeMessage = error.cause?.code || error.message || 'Unknown error';
    return NextResponse.json(
      { success: false, error: 'Login proxy failed', details: causeMessage },
      { status: 500 }
    );
  }
} 