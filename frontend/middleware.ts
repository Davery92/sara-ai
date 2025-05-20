import { NextResponse, type NextRequest } from 'next/server';
// import { getToken } from 'next-auth/jwt';
// import { guestRegex, isDevelopmentEnvironment } from './lib/constants';

// Only login, signup, and guest endpoints are truly public before authentication
const TRULY_PUBLIC_API_ROUTES = ['/api/auth/login', '/api/auth/signup', '/api/auth/guest'];
const PUBLIC_PAGES = ['/login', '/register'];

export async function middleware(request: NextRequest) {
  const { pathname, search, origin } = request.nextUrl;
  const fullPathWithQuery = pathname + search;

  console.log(`[MW] Path: ${pathname}`);

  // Temporarily allow /chat/ paths directly for debugging
  if (pathname.startsWith('/chat/')) {
    console.log('MIDDLEWARE: Allowing /chat/ path directly for debugging');
    return NextResponse.next();
  }

  /*
   * Playwright starts the dev server and requires a 200 status to
   * begin the tests, so this ensures that the tests can start
   */
  if (pathname.startsWith('/ping')) {
    return new Response('pong', { status: 200 });
  }

  // if (pathname.startsWith('/api/auth')) {
  //   return NextResponse.next();
  // }

  // const token = await getToken({
  //   req: request,
  //   secret: process.env.AUTH_SECRET,
  //   secureCookie: !isDevelopmentEnvironment,
  // });

  // if (!token) {
  //   const redirectUrl = encodeURIComponent(request.url);

  //   return NextResponse.redirect(
  //     new URL(`/api/auth/guest?redirectUrl=${redirectUrl}`, request.url),
  //   );
  // }

  // const isGuest = guestRegex.test(token?.email ?? '');

  // if (token && !isGuest && ['/login', '/register'].includes(pathname)) {
  //   return NextResponse.redirect(new URL('/', request.url));
  // }

  // 1. Allow Next.js internals, common static assets, and specific root files
  if (
    pathname.startsWith('/_next/') ||
    pathname.startsWith('/static/') ||
    pathname.match(/\.(?:png|jpg|jpeg|gif|svg|css|js|ico|webp|json|woff2|woff|ttf|otf)$/i) ||
    pathname === '/favicon.ico' ||
    pathname === '/robots.txt' ||
    pathname === '/sitemap.xml'
  ) {
    console.log(`[MW] Allowing asset/internal path: ${pathname}`);
    return NextResponse.next();
  }

  // 2. Allow /ping
  if (pathname === '/ping') {
    console.log(`[MW] Allowing ping path: ${pathname}`);
    return new Response('pong', { status: 200 });
  }

  // 3. Check for token in HttpOnly cookie
  const token = request.cookies.get('accessToken')?.value;
  console.log(`[MW] Token found in cookie: ${token ? 'Yes' : 'No'}`);

  // 4. Allow truly public API routes
  if (TRULY_PUBLIC_API_ROUTES.some(prefix => pathname.startsWith(prefix))) {
    console.log(`[MW] Allowing truly public API path: ${pathname}`);
    return NextResponse.next();
  }

  // 5. Handle behavior based on token presence
  if (token) {
    console.log(`[MW] User has token. Path: ${pathname}`);
    if (PUBLIC_PAGES.includes(pathname)) {
      console.log(`[MW] Authenticated user on public page ${pathname}, redirecting to /`);
      return NextResponse.redirect(new URL('/', origin));
    }
    console.log(`[MW] Authenticated user on path ${pathname}, allowing.`);
    return NextResponse.next();
  } else {
    console.log(`[MW] User has NO token. Path: ${pathname}`);
    if (PUBLIC_PAGES.includes(pathname)) {
      console.log(`[MW] Unauthenticated user on public page ${pathname}, allowing.`);
      return NextResponse.next();
    }

    // For other API routes (including me, logout, refresh)
    if (pathname.startsWith('/api/')) {
      console.log(`[MW] Unauthenticated user on protected API path ${pathname}, returning 401.`);
      return new NextResponse(JSON.stringify({ message: 'Authentication required' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      });
    } else {
      console.log(`[MW] Unauthenticated user on protected page ${pathname}, redirecting to login.`);
      const loginUrl = new URL('/login', origin);
      if (pathname !== '/') {
        loginUrl.searchParams.set('redirectUrl', fullPathWithQuery);
      }
      return NextResponse.redirect(loginUrl);
    }
  }
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|.*\\.(?:png|jpg|jpeg|gif|svg|css|js|ico|webp|json|woff2|woff|ttf|otf)$).*)',
    '/',
  ],
};
