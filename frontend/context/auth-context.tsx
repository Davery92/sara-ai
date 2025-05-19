'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';

interface User {
  // The user object reflects what the backend returns
  // For now, this is just the username (which is the email in our implementation)
  user: string;
  iat?: number;
}

interface AuthContextType {
  // accessToken: string | null; // Remove direct token access from context
  // refreshToken: string | null; // Remove direct token access from context
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  // login: (accessToken: string, refreshToken: string) => Promise<void>; // Modify login signature if needed
  login: () => Promise<void>;
  logout: () => void;
  refreshAuthToken: () => Promise<string | null>; // This might need re-evaluation if refresh token is also HttpOnly
  fetchUser: (isRetry?: boolean) => Promise<void>; // Corrected type definition
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Remove token states as they are now HttpOnly cookies
  // const [accessToken, setAccessToken] = useState<string | null>(null);
  // const [refreshToken, setRefreshToken] = useState<string | null>(null);

  const logout = useCallback(() => {
    setUser(null);
    
    // Clear sessionStorage tokens if they exist
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem('accessToken');
      sessionStorage.removeItem('refreshToken');
    }
    
    console.log('User logged out');
    // Trigger logout API route to clear HttpOnly cookies
    fetch('/api/auth/logout', { method: 'POST' });
  }, []);

  // Define refreshAuthToken first
  const refreshAuthToken: () => Promise<string | null> = useCallback(async () => {
    console.log('Attempting to refresh token...');
    
    try {
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        const data = await response.json();
        const newAccessToken = data.access_token;
        console.log('Token refreshed successfully via API.');
        // After refreshing, refetch user data as the access token has changed
        await fetchUser(); // Call fetchUser as a function
        return newAccessToken; 
      } else {
        console.error('Token refresh failed:', response.status, await response.text());
        logout(); 
        return null;
      }
    } catch (error) {
      console.error('Token refresh error (network or other issue):', error);
      logout();
      return null;
    }
  }, [logout]); // Temporarily omit fetchUser

  // Define fetchUser second, depending on refreshAuthToken
  const fetchUser: (isRetry?: boolean) => Promise<void> = useCallback(async (isRetry = false) => {
    console.log('[Auth Debug] fetchUser called');
    
    setIsLoading(true);
    try {
      console.log('[Auth Debug] Making request to /api/auth/me');
      
      // Check for token in sessionStorage for immediate use
      const sessionToken = typeof window !== 'undefined' ? sessionStorage.getItem('accessToken') : null;
      
      // Prepare headers if we have a token in sessionStorage
      const headers: HeadersInit = {};
      if (sessionToken) {
        console.log('[Auth Debug] Using token from sessionStorage');
        headers['Authorization'] = `Bearer ${sessionToken}`;
      }
      
      // Make the request to /api/auth/me with Authorization header if token exists
      const response = await fetch('/api/auth/me', 
        sessionToken ? { credentials: 'include', headers } : { credentials: 'include' }
      );
      
      console.log(`[Auth Debug] /api/auth/me response status: ${response.status}`);
      
      if (response.ok) {
        const userData = await response.json();
        console.log('[Auth Debug] User data received:', userData);
        setUser(userData);
      } else if (response.status === 401 && !isRetry) {
        console.log('/me returned 401, attempting token refresh.');
        // Call refreshAuthToken as a function
        const newAccessToken = await refreshAuthToken(); 
        if (newAccessToken) {
          console.log('Retrying /me after refresh.');
          await fetchUser(true); 
        } else {
          setUser(null);
        }
      } else {
        console.error('Failed to fetch user data, status:', response.status);
        setUser(null);
        if (response.status === 401) {
            logout();
        }
      }
    } catch (error) {
      console.error('Error fetching user data:', error);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, [logout, refreshAuthToken]); // Include refreshAuthToken in dependencies
  
  // Now add fetchUser to refreshAuthToken dependencies explicitly for clarity
  // The previous manual __deps assignment was incorrect. React handles this via dependency arrays.
  // We ensure fetchUser is defined before being a dependency here.
  // This line is removed as it's incorrect React hook usage.
  // (refreshAuthToken as any as React.DependencyList[number]).__deps = [logout, fetchUser];

  useEffect(() => {
    console.log('[Auth Debug] AuthProvider useEffect running');
    fetchUser();
  }, [fetchUser]);

  const login = useCallback(async () => {
    console.log('[Auth Debug] Login called in AuthContext');
    await fetchUser();
    console.log('[Auth Debug] Login process in AuthContext complete');
  }, [fetchUser]);

  return (
    <AuthContext.Provider value={{
      // accessToken, // Remove from value
      // refreshToken, // Remove from value
      user,
      isLoading,
      isAuthenticated: !!user, // Authenticated if user data is present
      login,
      logout,
      refreshAuthToken,
      fetchUser,
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}; 