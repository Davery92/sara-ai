import type { CoreAssistantMessage, CoreToolMessage, UIMessage } from 'ai';
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { Document } from '@/lib/db/schema';
import { ChatSDKError, type ErrorCode } from './errors';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const fetcher = async (url: string) => {
  const response = await fetch(url);

  if (!response.ok) {
    const { code, cause } = await response.json();
    throw new ChatSDKError(code as ErrorCode, cause);
  }

  return response.json();
};

export async function fetchWithErrorHandlers(
  input: RequestInfo | URL,
  init?: RequestInit,
) {
  try {
    const response = await fetch(input, init);

    if (!response.ok) {
      const { code, cause } = await response.json();
      throw new ChatSDKError(code as ErrorCode, cause);
    }

    return response;
  } catch (error: unknown) {
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      throw new ChatSDKError('offline:chat');
    }

    throw error;
  }
}

export function getLocalStorage(key: string) {
  if (typeof window !== 'undefined') {
    return JSON.parse(localStorage.getItem(key) || '[]');
  }
  return [];
}

export function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

type ResponseMessageWithoutId = CoreToolMessage | CoreAssistantMessage;
type ResponseMessage = ResponseMessageWithoutId & { id: string };

export function getMostRecentUserMessage(messages: Array<UIMessage>) {
  const userMessages = messages.filter((message) => message.role === 'user');
  return userMessages.at(-1);
}

export function getDocumentTimestampByIndex(
  documents: Array<Document>,
  index: number,
) {
  if (!documents) return new Date();
  if (index > documents.length) return new Date();

  return documents[index].createdAt;
}

export function getTrailingMessageId({
  messages,
}: {
  messages: Array<ResponseMessage>;
}): string | null {
  const trailingMessage = messages.at(-1);

  if (!trailingMessage) return null;

  return trailingMessage.id;
}

export function sanitizeText(text: string) {
  return text.replace('<has_function_call>', '');
}

// New function for authenticated API calls
export async function fetchWithAuth(
  input: RequestInfo | URL,
  init?: RequestInit,
  // authContext?: { accessToken: string | null; refreshToken: string | null; logout: () => void; refreshAuthToken: () => Promise<string | null> } // Optional: pass auth context if needed for refresh
) {
  let accessToken = typeof window !== 'undefined' ? localStorage.getItem('accessToken') : null;

  const makeRequest = async (token: string | null) => {
    const headers = new Headers(init?.headers);
    if (token) {
      headers.append('Authorization', `Bearer ${token}`);
    }

    const response = await fetch(input, {
      ...init,
      headers,
    });

    if (!response.ok) {
      if (response.status === 401 && token) {
        // Unauthorized, potentially token expired. Attempt to refresh.
        // For now, we'll just throw the error or log out as refresh is not fully implemented.
        // const newAccessToken = await authContext?.refreshAuthToken(); // If authContext was passed
        // if (newAccessToken) {
        //   return makeRequest(newAccessToken); // Retry with new token
        // }
        // If refresh fails or not implemented, throw or logout
        if (typeof window !== 'undefined') {
          // Basic logout if refresh fails or is not implemented by clearing tokens.
          // A more robust solution would use the logout function from AuthContext.
          localStorage.removeItem('accessToken');
          localStorage.removeItem('refreshToken');
          // Consider redirecting to login: window.location.href = '/login';
        }
        const errorData = await response.json().catch(() => ({ code: 'unauthorized', cause: 'Token expired or invalid' }));
        throw new ChatSDKError(errorData.code || 'unauthorized', errorData.cause || 'Token expired or invalid after attempting refresh (stubbed)');
      }
      const { code, cause } = await response.json().catch(() => ({ code: 'fetch_error', cause: 'Unknown error' }));
      throw new ChatSDKError(code as ErrorCode, cause);
    }
    return response;
  };

  return makeRequest(accessToken);
}
