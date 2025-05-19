import { NextRequest, NextResponse } from 'next/server';
import { getApiBaseUrl } from '@/lib/get-api-base-url';

/**
 * Proxy route for chats via the backend gateway
 */

// GET /v1/chats
export async function GET(request: NextRequest) {
  const accessToken = request.cookies.get('accessToken')?.value;

  if (!accessToken) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const serverApiBaseUrl = getApiBaseUrl('server');
  const gatewayChatsUrl = `${serverApiBaseUrl}/api/chats`;

  console.log(`[FRONTEND /v1/chats] Proxying GET request to: ${gatewayChatsUrl}`);

  try {
    const response = await fetch(gatewayChatsUrl, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      cache: 'no-store',
    });

    if (!response.ok) {
      const errorBody = await response.text();
      console.error(`[FRONTEND /v1/chats] Error from gateway ${response.status}:`, errorBody);
      return NextResponse.json(
        { error: 'Failed to fetch chats from backend', details: errorBody },
        { status: response.status }
      );
    }

    const chatsData = await response.json();
    return NextResponse.json(chatsData);
  } catch (error: any) {
    console.error(`[FRONTEND /v1/chats] Error proxying GET request:`, error);
    let causeMessage = 'Unknown cause';
    if (error.cause && typeof error.cause === 'object' && 'code' in error.cause) {
      causeMessage = `Network error: ${error.cause.code}`;
    } else if (error.message) {
      causeMessage = error.message;
    }
    return NextResponse.json(
      { error: 'Failed to proxy chat list request', details: causeMessage },
      { status: 500 }
    );
  }
}

// POST /v1/chats
export async function POST(request: NextRequest) {
  const accessToken = request.cookies.get('accessToken')?.value;

  if (!accessToken) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const serverApiBaseUrl = getApiBaseUrl('server');
  const gatewayCreateChatUrl = `${serverApiBaseUrl}/api/chats`;

  console.log(`[FRONTEND /v1/chats] Proxying POST request to: ${gatewayCreateChatUrl}`);

  try {
    const requestBody = await request.json();
    const response = await fetch(gatewayCreateChatUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
      cache: 'no-store',
    });

    const responseData = await response.json();
    if (!response.ok) {
      console.error(`[FRONTEND /v1/chats] Error from gateway POST ${response.status}:`, responseData);
      return NextResponse.json(
        { error: 'Failed to create chat via backend', details: responseData.detail || responseData },
        { status: response.status }
      );
    }
    return NextResponse.json(responseData, { status: response.status });
  } catch (error: any) {
    console.error(`[FRONTEND /v1/chats] Error proxying POST request:`, error);
    let causeMessage = 'Unknown cause';
    if (error.cause && typeof error.cause === 'object' && 'code' in error.cause) {
      causeMessage = `Network error: ${error.cause.code}`;
    } else if (error.message) {
      causeMessage = error.message;
    }
    return NextResponse.json(
      { error: 'Failed to proxy chat creation request', details: causeMessage },
      { status: 500 }
    );
  }
} 