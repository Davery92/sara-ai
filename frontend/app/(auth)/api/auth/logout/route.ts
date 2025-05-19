import { NextRequest, NextResponse } from 'next/server';

/**
 * Handle logout requests by clearing cookies
 */

export async function POST(request: NextRequest) {
  // Create a response
  const response = NextResponse.json({ success: true });
  
  // Clear all auth cookies
  response.cookies.set({
    name: 'accessToken',
    value: '',
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    maxAge: 0,
    path: '/',
  });
  
  response.cookies.set({
    name: 'refreshToken',
    value: '',
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    maxAge: 0,
    path: '/',
  });
  
  console.log('[API/LOGOUT] Cleared auth cookies');
  return response;
} 