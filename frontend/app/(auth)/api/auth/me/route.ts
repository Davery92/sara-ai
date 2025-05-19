import { NextRequest, NextResponse } from 'next/server';
import { getApiBaseUrl } from '@/lib/get-api-base-url';

/**
 * Handle user profile requests and forward them to the backend API
 */

export async function GET(request: NextRequest) {
  try {
    // Extract access token from HttpOnly cookie
    const accessToken = request.cookies.get('accessToken')?.value;
    if (!accessToken) {
      return NextResponse.json({ error: 'Authentication required' }, { status: 401 });
    }

    // Determine backend URL
    const serverApiBaseUrl = getApiBaseUrl('server');
    const backendMeUrl = `${serverApiBaseUrl}/auth/me`;
    console.log(`[API/ME] Proxying to backend at: ${backendMeUrl}`);

    // Forward request to backend with Authorization header
    const backendResponse = await fetch(backendMeUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
    });

    const data = await backendResponse.json();
    if (!backendResponse.ok) {
      return NextResponse.json({ error: data.detail || 'Failed to fetch user' }, { status: backendResponse.status });
    }

    // Return user data
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('[API/ME] Error in auth/me route:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
} 