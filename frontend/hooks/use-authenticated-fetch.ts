'use client';

import { useCallback } from 'react';
import { useAuth } from '@/context/auth-context';
import { ChatSDKError, type ErrorCode } from '@/lib/errors';
import { getApiBaseUrl } from '@/lib/get-api-base-url';

interface AuthenticatedFetchOptions extends RequestInit {
  // We can add specific options if needed in the future
}

export function useAuthenticatedFetch() {
  const { getFreshAccessToken, logout } = useAuth();

  const authenticatedFetch = useCallback(
    async (input: RequestInfo | URL, options?: AuthenticatedFetchOptions): Promise<Response> => {
      // Handle relative and absolute URLs
      let url = input instanceof URL ? input.toString() : input;
      
      // For relative URLs that don't start with http/https, use the base API URL
      if (typeof url === 'string' && !url.startsWith('http')) {
        const baseApiUrl = getApiBaseUrl('client');
        // Remove leading slash from url if present to avoid double slashes
        const cleanPath = url.startsWith('/') ? url.slice(1) : url;
        url = `${baseApiUrl}/${cleanPath}`;
        console.log('AUTHENTICATED_FETCH: Constructed URL:', url);
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
            const newAccessToken = await getFreshAccessToken();
            if (newAccessToken) {
              console.log('Token refreshed successfully. Retrying original request...');
              return makeRequest(newAccessToken); // Retry with the new token
            } else {
              // Refresh failed, logout would have been called by getFreshAccessToken
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

      // Get a fresh token for the initial request
      const initialToken = await getFreshAccessToken();
      return makeRequest(initialToken);
    },
    [getFreshAccessToken, logout],
  );

  return { authenticatedFetch };
} 