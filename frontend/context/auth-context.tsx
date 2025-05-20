'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback, useRef } from 'react';

// User object reflecting the backend JWT 'sub' claim
interface User {
  user: string;
  iat?: number;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean; // Represents overall auth state loading (e.g., initial check)
  isAuthenticated: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  fetchUser: () => Promise<boolean>; // Simplified: no isRetry needed if managed internally
  getFreshAccessToken: () => Promise<string | null>; // New function
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true); // True during initial auth check
  
  // Ref to prevent multiple concurrent fetchUser operations
  const fetchUserPromiseRef = useRef<Promise<boolean> | null>(null);

  const performLogout = useCallback(async () => {
    console.log('[AuthContext] performLogout called.');
    setUser(null);
    setIsLoading(false); // After logout, we are no longer "loading" auth state
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
      console.log('[AuthContext] Logout API call successful.');
    } catch (error) {
      console.error('[AuthContext] Error during logout API call:', error);
    }
  }, []);

  const fetchUserData = useCallback(async (attemptRefresh = true): Promise<boolean> => {
    console.log(`[AuthContext] fetchUserData called (attemptRefresh: ${attemptRefresh})`);
    
    try {
      const response = await fetch('/api/auth/me', { credentials: 'include' });
      console.log(`[AuthContext] /api/auth/me response status: ${response.status}`);

      if (response.ok) {
        const userData = await response.json();
        console.log('[AuthContext] User data received:', userData);
        setUser(userData);
        return true;
      } else if (response.status === 401 && attemptRefresh) {
        console.log('[AuthContext] /api/auth/me 401. Attempting token refresh.');
        const refreshResponse = await fetch('/api/auth/refresh', {
          method: 'POST',
          credentials: 'include',
        });
        console.log(`[AuthContext] /api/auth/refresh response status: ${refreshResponse.status}`);
        if (refreshResponse.ok) {
          console.log('[AuthContext] Token refresh successful. Retrying fetchUser (no further refresh).');
          return await fetchUserData(false); // Retry fetchUser, but don't attempt refresh again
        } else {
          console.log('[AuthContext] Token refresh failed.');
          await performLogout();
          return false;
        }
      } else { // Non-401 error, or 401 after refresh attempt
        console.log(`[AuthContext] Failed to fetch user or unhandled status: ${response.status}`);
        if (response.status === 401) {
            await performLogout();
        } else {
            setUser(null); // For other errors, clear user but don't necessarily full logout immediately
        }
        return false;
      }
    } catch (error) {
      console.error('[AuthContext] Network or other error in fetchUserData:', error);
      await performLogout();
      return false;
    }
  }, [performLogout]);


  const fetchUser = useCallback(async (): Promise<boolean> => {
    // If a fetchUser operation is already in progress, return that promise
    if (fetchUserPromiseRef.current) {
      console.log('[AuthContext] fetchUser: Existing operation in progress, returning its promise.');
      return fetchUserPromiseRef.current;
    }

    console.log('[AuthContext] fetchUser: Starting new operation.');
    setIsLoading(true);
    
    const promise = fetchUserData()
      .finally(() => {
        setIsLoading(false);
        fetchUserPromiseRef.current = null; // Clear the ref once done
        console.log('[AuthContext] fetchUser: Operation finished.');
      });
    
    fetchUserPromiseRef.current = promise;
    return promise;
  }, [fetchUserData]);


  useEffect(() => {
    console.log('[AuthContext] Initializing: fetching user on mount.');
    fetchUser();
  }, [fetchUser]); // fetchUser is memoized

  const login = useCallback(async () => {
    console.log('[AuthContext] login() called. Triggering fetchUser.');
    // isLoading will be set by fetchUser if it starts a new operation
    await fetchUser(); 
  }, [fetchUser]);

  // New function to get a fresh access token
  const getFreshAccessToken = useCallback(async (): Promise<string | null> => {
    console.log('[AuthContext] getFreshAccessToken called.');
    if (!user) { // Or a more direct check if refresh token cookie exists if possible
        console.warn('[AuthContext] getFreshAccessToken: User not authenticated, cannot refresh.');
        // Try one initial fetchUser in case auth state is just latent
        const success = await fetchUser();
        if (!success) return null;
    }

    try {
      const refreshResponse = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include', // Sends HttpOnly refreshToken cookie
      });
      console.log(`[AuthContext] getFreshAccessToken: /api/auth/refresh response status: ${refreshResponse.status}`);
      if (refreshResponse.ok) {
        const data = await refreshResponse.json();
        // IMPORTANT: We are returning the token from the JSON body here,
        // not relying on the HttpOnly cookie it also sets.
        console.log('[AuthContext] getFreshAccessToken: Token refresh successful, returning new accessToken from JSON.');
        // After refreshing, it's good practice to ensure user state is up-to-date.
        // No need to await this if the primary goal is to get the token for WS.
        fetchUser(); 
        return data.access_token;
      } else {
        console.error('[AuthContext] getFreshAccessToken: Token refresh failed.');
        await performLogout();
        return null;
      }
    } catch (error) {
      console.error('[AuthContext] getFreshAccessToken: Error during token refresh:', error);
      await performLogout();
      return null;
    }
  }, [user, fetchUser, performLogout]); // Added user and fetchUser

  return (
    <AuthContext.Provider value={{
      user,
      isLoading,
      isAuthenticated: !!user,
      login,
      logout: performLogout,
      fetchUser,
      getFreshAccessToken, // Expose the new function
    }}>
      {children}
    </AuthContext.Provider>
  );
};

// Custom hook to consume AuthContext
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}; 