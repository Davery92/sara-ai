import { NextRequest, NextResponse } from 'next/server';
import { getApiBaseUrl } from '@/lib/get-api-base-url';

/**
 * Handle user profile requests and forward them to the backend API
 */

export async function GET(request: NextRequest) {
  // Log request details
  console.log("[SERVER] /api/auth/me called");
  
  try {
    const authorization = request.headers.get('authorization');
    
    if (!authorization) {
      // Try to get token from cookie as fallback
      const token = request.cookies.get('accessToken')?.value;
      if (token) {
        // Create Authorization header from cookie token
        const cookieAuth = `Bearer ${token}`;
        console.log("[SERVER] Using token from cookie for auth");
        
        // Forward the request to the backend with the Authorization header from cookie
        const response = await fetch(`${getApiBaseUrl('server')}/auth/me`, {
          method: 'GET',
          headers: {
            'Authorization': cookieAuth,
          },
        });
        
        if (!response.ok) {
          console.error(`[SERVER] Backend auth/me error with cookie token (${response.status})`);
          return NextResponse.json(
            { error: 'Authentication failed' }, 
            { status: response.status }
          );
        }
        
        const data = await response.json();
        return NextResponse.json(data);
      }
      
      // No auth header and no cookie token
      return NextResponse.json(
        { error: 'Authorization header missing and no cookie token found' }, 
        { status: 401 }
      );
    }
    
    // Forward the request to our backend with the Authorization header
    console.log("[SERVER] Using Authorization header for auth");
    const backendApiUrl = `${getApiBaseUrl('server')}/auth/me`;
    console.log("[SERVER] Calling backend at:", backendApiUrl);
    
    const response = await fetch(backendApiUrl, {
      method: 'GET',
      headers: {
        'Authorization': authorization,
      },
    });
    
    if (!response.ok) {
      let errorData;
      try {
        errorData = await response.json();
        console.error(`[SERVER] Backend auth/me error (${response.status}):`, errorData);
      } catch (e) {
        errorData = await response.text();
        console.error(`[SERVER] Backend auth/me error (${response.status}):`, errorData);
      }
      
      return NextResponse.json(
        { error: 'Failed to authenticate with backend' }, 
        { status: response.status }
      );
    }
    
    const data = await response.json();
    return NextResponse.json(data);
    
  } catch (error) {
    console.error('[SERVER] Error in /api/auth/me:', error);
    return NextResponse.json(
      { error: 'Server error in auth/me route', details: String(error) }, 
      { status: 500 }
    );
  }
} 