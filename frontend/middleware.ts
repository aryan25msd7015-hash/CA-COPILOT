import { NextRequest, NextResponse } from 'next/server';
import {
  DESK_COOKIE,
  DESK_CONFIG,
  DESK_HEADER,
  deskFromHost,
  deskHome,
  isPathAllowedForDesk,
  type AppDesk,
} from '@/lib/roleDomains';

function withDeskHeaders(response: NextResponse, desk: AppDesk): NextResponse {
  response.headers.set(DESK_HEADER, desk);
  response.cookies.set(DESK_COOKIE, desk, {
    path: '/',
    sameSite: 'lax',
    httpOnly: false,
  });
  return response;
}

export function middleware(request: NextRequest) {
  const host = request.headers.get('host') || request.nextUrl.host;
  const desk = deskFromHost(host);
  const { pathname } = request.nextUrl;

  // Always stamp desk identity for the request.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(DESK_HEADER, desk);

  if (desk === 'hub') {
    return withDeskHeaders(
      NextResponse.next({ request: { headers: requestHeaders } }),
      'hub',
    );
  }

  // Client desk: portal only.
  if (desk === 'client') {
    if (pathname === '/' || pathname === '/login') {
      const url = request.nextUrl.clone();
      url.pathname = '/client-portal/login';
      return withDeskHeaders(NextResponse.redirect(url), desk);
    }
    if (!isPathAllowedForDesk(desk, pathname)) {
      const url = request.nextUrl.clone();
      url.pathname = DESK_CONFIG.client.home;
      return withDeskHeaders(NextResponse.redirect(url), desk);
    }
    return withDeskHeaders(
      NextResponse.next({ request: { headers: requestHeaders } }),
      desk,
    );
  }

  // Firm role desks: lock to that role's surface.
  if (pathname === '/') {
    const url = request.nextUrl.clone();
    url.pathname = deskHome(desk);
    return withDeskHeaders(NextResponse.redirect(url), desk);
  }

  if (!isPathAllowedForDesk(desk, pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = deskHome(desk);
    return withDeskHeaders(NextResponse.redirect(url), desk);
  }

  return withDeskHeaders(
    NextResponse.next({ request: { headers: requestHeaders } }),
    desk,
  );
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
};
