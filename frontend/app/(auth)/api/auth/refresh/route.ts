import { NextRequest, NextResponse } from 'next/server';
import { getApiBaseUrl } from '@/lib/get-api-base-url'; // Assuming this is the correct path

/**
 * Handle token refresh requests and forward them to the backend API
 */

export async function POST(request: NextRequest) {
  try {
    let refresh_token;
    
    // Try to get refresh token from HttpOnly cookie first (more secure)
    refresh_token = request.cookies.get('refreshToken')?.value;
    console.log(`[API/REFRESH] refreshToken from cookie: ${refresh_token ? 'Found' : 'Not Found'}`);

    if (!refresh_token) {
      // Fallback: try getting from request body (less common if using HttpOnly cookies properly)
      try {
        const body = await request.json();
        refresh_token = body.refresh_token;
        console.log(`[API/REFRESH] refreshToken from body: ${refresh_token ? 'Found' : 'Not Found'}`);
      } catch (e) {
        console.log('[API/REFRESH] No JSON body or refresh_token in body.');
      }
    }
    
    if (!refresh_token) {
      console.log('[API/REFRESH] Refresh token is required, not found in cookie or body.');
      return NextResponse.json({ error: 'Refresh token is required' }, { status: 400 });
    }
    
    const serverApiBaseUrl = getApiBaseUrl('server'); // Use for backend call
    const backendRefreshUrl = `${serverApiBaseUrl}/auth/refresh`;
    console.log(`[API/REFRESH] Calling backend at: ${backendRefreshUrl}`);

    const backendResponse = await fetch(backendRefreshUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token }), // Backend expects refresh_token in body
    });
    
    const data = await backendResponse.json();
    
    if (!backendResponse.ok) {
      console.error(`[API/REFRESH] Backend refresh error (${backendResponse.status}):`, data.detail || data);
      return NextResponse.json(
        { error: data.detail || 'Token refresh failed at backend' },
        { status: backendResponse.status }
      );
    }
    
    // Create a new response to set cookies
    const responseWithCookies = NextResponse.json(data); // data should contain new access_token
    
    const requestProtocol = request.headers.get('x-forwarded-proto') || request.nextUrl.protocol.replace(':', '');
    const isConnectionSecure = requestProtocol === 'https';
    const cookieSecureFlag = isConnectionSecure; // Simplified for local dev
    console.log(`[API/REFRESH] Cookie Secure Flag will be: ${cookieSecureFlag}`);

    if (data.access_token) {
      responseWithCookies.cookies.set({
        name: 'accessToken',
        value: data.access_token,
        httpOnly: true,
        secure: cookieSecureFlag,
        sameSite: 'lax',
        maxAge: 60 * 60 * 24 * 7, 
        path: '/'
      });
    }
    // Note: The backend refresh might also return a new refresh_token. If so, update it.
    if (data.refresh_token) {
         responseWithCookies.cookies.set({
            name: 'refreshToken',
            value: data.refresh_token,
            httpOnly: true,
            secure: cookieSecureFlag,
            sameSite: 'strict',
            maxAge: 60 * 60 * 24 * 30,
            path: '/'
        });
    }
    
    console.log('[API/REFRESH] Token refresh successful, returning new tokens (accessToken in JSON, both as cookies).');
    return responseWithCookies;

  } catch (error: any) { // Catch any error, including JSON parsing or network issues
    console.error('[API/REFRESH] Error in refresh route handler:', error);
    let causeMessage = error.message || 'Unknown error during refresh';
    if (error.cause) causeMessage = `${causeMessage} (Cause: ${error.cause})`;
    return NextResponse.json(
      { error: 'Token refresh proxy failed', details: causeMessage },
      { status: 500 } // Return 500 for internal errors in this route
    );
  }
} 