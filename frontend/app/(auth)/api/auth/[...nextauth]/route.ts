import { NextRequest, NextResponse } from 'next/server';

/**
 * Handle Next.js auth callbacks 
 * This is a simplified handler that redirects to our custom auth pages
 */

export function GET(request: NextRequest) {
  // Extract any callback URL from the request
  const searchParams = request.nextUrl.searchParams;
  const callbackUrl = searchParams.get('callbackUrl');
  
  // Redirect to login page with callback URL if provided
  if (callbackUrl) {
    return NextResponse.redirect(new URL(`/login?callbackUrl=${encodeURIComponent(callbackUrl)}`, request.url));
  }
  
  // Otherwise redirect to login page
  return NextResponse.redirect(new URL('/login', request.url));
}

export function POST(request: NextRequest) {
  // For POST requests, redirect to login page to use our custom forms
  return NextResponse.redirect(new URL('/login', request.url));
}
