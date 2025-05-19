import { NextResponse, type NextRequest } from 'next/server';
// import { getToken } from 'next-auth/jwt';
// import { guestRegex, isDevelopmentEnvironment } from './lib/constants';

const PUBLIC_API_PREFIXES = ['/api/auth/login', '/api/auth/signup', '/api/auth/refresh', '/api/auth/me', '/api/auth/logout'];
const PUBLIC_PAGES = ['/login', '/register'];

export async function middleware(request: NextRequest) {
  const { pathname, search, origin } = request.nextUrl;
  const fullPathWithQuery = pathname + search;

  console.log(`MIDDLEWARE: Processing path: ${pathname}`);

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

  // 1. Allow Next.js internals, common static assets, and specific public files unconditionally
  if (
    pathname.startsWith('/_next/') ||
    pathname.startsWith('/static/') || // If you have a /static folder
    // pathname.startsWith('/public/') || // Serving from /public is default Next.js behavior, covered by asset check
    pathname === '/favicon.ico' ||
    pathname === '/robots.txt' ||
    pathname === '/sitemap.xml' ||
    pathname.match(/\.(?:png|jpg|jpeg|gif|svg|css|js|ico|webp|json|woff2|woff|ttf|otf)$/i) // Common asset extensions
  ) {
    console.log(`MIDDLEWARE: Allowing asset/internal path: ${pathname}`);
    return NextResponse.next();
  }

  // 2. Allow /ping
  if (pathname === '/ping') {
    console.log(`MIDDLEWARE: Allowing ping path: ${pathname}`);
    return new Response('pong', { status: 200 });
  }

  // 3. Check for token in both cookie and Authorization header
  const cookieToken = request.cookies.get('accessToken')?.value;
  const authHeader = request.headers.get('authorization');
  const token = cookieToken || (authHeader?.startsWith('Bearer ') ? authHeader.substring(7) : null);
  console.log(`MIDDLEWARE: Token found: ${token ? 'Yes' : 'No'}`);

  // 4. Handle public API routes (these are allowed regardless of token state)
  if (PUBLIC_API_PREFIXES.some(prefix => pathname.startsWith(prefix))) {
    console.log(`MIDDLEWARE: Allowing public API path: ${pathname}`);
    return NextResponse.next();
  }

  // 5. Handle behavior based on token presence
  if (token) {
    console.log(`MIDDLEWARE: User has token. Path: ${pathname}`);
    // User has a token
    if (PUBLIC_PAGES.includes(pathname)) {
      console.log(`MIDDLEWARE: Authenticated user on public page ${pathname}, redirecting to /`);
      // Authenticated user trying to access login/register page, redirect to home
      return NextResponse.redirect(new URL('/', origin));
    }
    // For any other path (protected pages or API routes not covered by PUBLIC_API_PREFIXES),
    // let the request proceed. API endpoints should validate the token separately.
    console.log(`MIDDLEWARE: Authenticated user on protected path ${pathname}, allowing.`);
    return NextResponse.next();
  } else {
    console.log(`MIDDLEWARE: User has no token. Path: ${pathname}`);
    // No token
    if (PUBLIC_PAGES.includes(pathname)) {
      console.log(`MIDDLEWARE: Unauthenticated user on public page ${pathname}, allowing.`);
      // Unauthenticated user trying to access login/register page, allow
      return NextResponse.next();
    }

    // No token and trying to access a protected route
    if (pathname.startsWith('/api/')) {
      console.log(`MIDDLEWARE: Unauthenticated user on protected API path ${pathname}, returning 401.`);
      // For protected API routes (not in PUBLIC_API_PREFIXES), return 401
      return new NextResponse(JSON.stringify({ message: 'Authentication required' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      });
    } else {
      console.log(`MIDDLEWARE: Unauthenticated user on protected page ${pathname}, redirecting to login.`);
      // For protected page routes, redirect to login
      const loginUrl = new URL('/login', origin);
      if (pathname !== '/') { // Avoid adding redirectUrl if already going to root and then login
        loginUrl.searchParams.set('redirectUrl', fullPathWithQuery);
      }
      return NextResponse.redirect(loginUrl);
    }
  }
}

export const config = {
  matcher: [
    '/',
    '/chat/:id*', // ensure dynamic chat routes and sub-paths are covered
    '/api/:path*',
    '/login',
    '/register',
    '/ping',
    // Match all request paths except for the ones starting with _next/static, _next/image, or specific root files.
    // Corrected the regex from the original template if it had issues.
    '/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)',
  ],
};
