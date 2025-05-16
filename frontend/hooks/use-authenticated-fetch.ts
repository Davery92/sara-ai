'use client';

import { useCallback } from 'react';
import { useAuth } from '@/context/auth-context';
import { ChatSDKError, type ErrorCode } from '@/lib/errors';

interface AuthenticatedFetchOptions extends RequestInit {
  // We can add specific options if needed in the future
}

export function useAuthenticatedFetch() {
  const { accessToken, refreshAuthToken, logout } = useAuth();

  const authenticatedFetch = useCallback(
    async (input: RequestInfo | URL, options?: AuthenticatedFetchOptions): Promise<Response> => {
      let currentToken = accessToken;

      // Handle relative and absolute URLs
      let url = input instanceof URL ? input.toString() : input;
      
      // For relative URLs that don't start with http/https, use the base API URL
      if (typeof url === 'string' && !url.startsWith('http') && !url.startsWith('/')) {
        const baseApiUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || '/v1';
        url = baseApiUrl.startsWith('http') 
          ? `${baseApiUrl}/${url}` 
          : `${baseApiUrl}/${url}`;
      }
      
      const makeRequest = async (tokenToUse: string | null): Promise<Response> => {
        const headers = new Headers(options?.headers);
        if (tokenToUse) {
          headers.append('Authorization', `Bearer ${tokenToUse}`);
        }

        const response = await fetch(url, {
          ...options,
          headers,
        });

        if (!response.ok) {
          if (response.status === 401 && tokenToUse) {
            console.log('Authenticated fetch received 401. Attempting token refresh...');
            const newAccessToken = await refreshAuthToken();
            if (newAccessToken) {
              console.log('Token refreshed successfully. Retrying original request...');
              return makeRequest(newAccessToken); // Retry with the new token
            } else {
              // Refresh failed, logout would have been called by refreshAuthToken
              // Throw an error to signal the request ultimately failed
              throw new ChatSDKError('unauthorized:auth', 'Session expired or refresh failed.');
            }
          }
          // For other errors or if no token was present initially for a 401
          const errorData = await response.json().catch(() => ({
            code: 'fetch_error',
            cause: `Request failed with status ${response.status}`,
          }));
          const errorCodeToUse = errorData.code && errorData.code.includes(':') ? errorData.code as ErrorCode : 'bad_request:api';
          throw new ChatSDKError(errorCodeToUse, errorData.cause);
        }
        return response;
      };

      return makeRequest(currentToken);
    },
    [accessToken, refreshAuthToken, logout],
  );

  return { authenticatedFetch };
} 