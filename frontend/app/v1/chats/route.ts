import { NextRequest, NextResponse } from 'next/server';
import { generateUUID } from '@/lib/utils';

/**
 * API route that returns a list of user chats
 * This is a temporary solution until the backend API is ready
 */

export async function GET(request: NextRequest) {
  // Get the authentication token from the request headers
  const auth = request.headers.get('authorization');
  
  // If no auth token, return an empty list
  if (!auth) {
    return NextResponse.json({
      chats: []
    });
  }
  
  // Return a list of mock chats for development
  return NextResponse.json({
    chats: [
      {
        id: generateUUID(),
        title: 'Sample Chat 1',
        createdAt: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
        updatedAt: new Date().toISOString(),
        messageCount: 8,
        visibility: 'private'
      },
      {
        id: generateUUID(),
        title: 'Programming Help',
        createdAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
        updatedAt: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
        messageCount: 12,
        visibility: 'private'
      }
    ]
  });
} 