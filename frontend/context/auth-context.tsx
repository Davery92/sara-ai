'use client';

import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';

interface User {
  // The user object reflects what the backend returns
  // For now, this is just the username (which is the email in our implementation)
  user: string;
  iat?: number;
}

interface AuthContextType {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (accessToken: string, refreshToken: string) => Promise<void>;
  logout: () => void;
  refreshAuthToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const logout = useCallback(() => {
    setAccessToken(null);
    setRefreshToken(null);
    setUser(null);
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    console.log('User logged out');
  }, []);

  const refreshAuthToken = useCallback(async (): Promise<string | null> => {
    console.log('Attempting to refresh token...');
    const currentRefreshToken = localStorage.getItem('refreshToken');

    if (!currentRefreshToken) {
      console.log('No refresh token found, logging out.');
      logout();
      return null;
    }

    try {
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: currentRefreshToken }),
      });

      if (response.ok) {
        const data = await response.json();
        const newAccessToken = data.access_token;
        const newRefreshToken = data.refresh_token;

        setAccessToken(newAccessToken);
        localStorage.setItem('accessToken', newAccessToken);
        
        if (newRefreshToken) {
          setRefreshToken(newRefreshToken);
          localStorage.setItem('refreshToken', newRefreshToken);
          console.log('Token refreshed successfully, new refresh token received.');
        } else {
          console.log('Token refreshed successfully, using existing refresh token.');
        }
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
  }, [logout]);

  const fetchAndSetUser = useCallback(async (token: string, isRetry = false) => {
    console.log(`[Auth Debug] fetchAndSetUser called with token: ${token ? token.substring(0, 10) + '...' : 'none'}`);
    
    try {
      console.log('[Auth Debug] Making request to /api/auth/me');
      
      // Log the full token for debugging (you should remove this in production)
      console.log('[Auth Debug] Full token being sent:', token);
      
      const response = await fetch('/api/auth/me', { 
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      
      console.log(`[Auth Debug] /api/auth/me response status: ${response.status}`);
      
      if (response.ok) {
        const userData = await response.json();
        console.log('[Auth Debug] User data received:', userData);
        setUser(userData);
      } else if (response.status === 401 && !isRetry) {
        console.log('/me returned 401, attempting token refresh.');
        
        // Try to see what the error response contains
        try {
          const errorData = await response.json();
          console.log('[Auth Debug] Error response data:', errorData);
        } catch (e) {
          console.log('[Auth Debug] Could not parse error response:', e);
        }
        
        const newAccessToken = await refreshAuthToken();
        if (newAccessToken) {
          console.log('Retrying /me with new access token.');
          await fetchAndSetUser(newAccessToken, true);
        } else {
          setUser(null);
        }
      } else {
        console.error('Failed to fetch user data, status:', response.status);
        
        // Try to parse error response for more details
        try {
          const errorData = await response.json();
          console.log('[Auth Debug] Error response details:', errorData);
        } catch (e) {
          console.log('[Auth Debug] Could not parse error response');
        }
        
        setUser(null);
        if (response.status === 401 && isRetry) {
            logout();
        }
      }
    } catch (error) {
      console.error('Error fetching user data:', error);
      setUser(null);
    }
  }, [refreshAuthToken, logout]);

  useEffect(() => {
    const loadTokensAndUser = async () => {
      setIsLoading(true);
      try {
        const storedAccessToken = localStorage.getItem('accessToken');
        const storedRefreshToken = localStorage.getItem('refreshToken');

        if (storedAccessToken && storedRefreshToken) {
          console.log('[Auth Debug] Found tokens in localStorage, setting up auth state');
          setAccessToken(storedAccessToken);
          setRefreshToken(storedRefreshToken);
          await fetchAndSetUser(storedAccessToken);
        } else {
          console.log('[Auth Debug] No tokens found in localStorage');
          setUser(null);
        }
      } catch (error) {
        console.error('Failed to load tokens or user from storage', error);
        setUser(null); 
      } finally {
        setIsLoading(false);
      }
    };
    loadTokensAndUser();
  }, [fetchAndSetUser]);

  const login = async (newAccessToken: string, newRefreshToken: string) => {
    console.log('[Auth Debug] Login called with tokens');
    console.log(`[Auth Debug] Access token: ${newAccessToken.substring(0, 10)}...`);
    console.log(`[Auth Debug] Refresh token: ${newRefreshToken.substring(0, 10)}...`);
    
    setIsLoading(true);
    setAccessToken(newAccessToken);
    setRefreshToken(newRefreshToken);
    localStorage.setItem('accessToken', newAccessToken);
    localStorage.setItem('refreshToken', newRefreshToken);
    
    console.log('[Auth Debug] Calling fetchAndSetUser');
    await fetchAndSetUser(newAccessToken);
    console.log('[Auth Debug] fetchAndSetUser completed');
    
    setIsLoading(false);
    console.log('[Auth Debug] Login process complete, authenticated:', !!user);
  };

  return (
    <AuthContext.Provider value={{
      accessToken,
      refreshToken,
      user,
      isLoading,
      isAuthenticated: !!accessToken && !!user,
      login,
      logout,
      refreshAuthToken
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