import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authService } from '../services/api';
import { jwtDecode } from 'jwt-decode';

interface User {
  username: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  signup: (username: string, password: string) => Promise<void>;
  logout: () => void;
  checkAndRefreshToken: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{children: ReactNode}> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  
  // Check if user is already logged in on initial load
  useEffect(() => {
    const checkAuth = async () => {
      try {
        await checkAndRefreshToken();
      } catch (error) {
        console.error('Auth check failed:', error);
        authService.logout();
      }
    };
    
    checkAuth();
  }, []);
  
  // Function to check token and refresh if needed
  const checkAndRefreshToken = async () => {
    const token = localStorage.getItem('accessToken');
    if (!token) {
      setUser(null);
      setIsAuthenticated(false);
      return;
    }
    
    try {
      const decoded: any = jwtDecode(token);
      
      // Check if token is expired
      if (decoded.exp < Date.now() / 1000) {
        console.log('Token expired, attempting refresh');
        // Try to use refresh token
        try {
          await authService.refreshToken();
          const newToken = localStorage.getItem('accessToken');
          if (newToken) {
            const newDecoded: any = jwtDecode(newToken);
            setUser({ username: newDecoded.sub });
            setIsAuthenticated(true);
          }
        } catch (refreshError) {
          console.error('Failed to refresh token:', refreshError);
          // Clear auth state if refresh fails
          authService.logout();
          setUser(null);
          setIsAuthenticated(false);
        }
      } else {
        // Token is still valid
        setUser({ username: decoded.sub });
        setIsAuthenticated(true);
      }
    } catch (error) {
      console.error('Invalid token:', error);
      authService.logout();
      setUser(null);
      setIsAuthenticated(false);
    }
  };
  
  // Login function
  const login = async (username: string, password: string) => {
    try {
      await authService.login(username, password);
      const token = localStorage.getItem('accessToken');
      if (token) {
        const decoded: any = jwtDecode(token);
        setUser({ username: decoded.sub });
        setIsAuthenticated(true);
      }
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  };
  
  // Signup function
  const signup = async (username: string, password: string) => {
    try {
      await authService.signup(username, password);
      const token = localStorage.getItem('accessToken');
      if (token) {
        const decoded: any = jwtDecode(token);
        setUser({ username: decoded.sub });
        setIsAuthenticated(true);
      }
    } catch (error) {
      console.error('Signup failed:', error);
      throw error;
    }
  };
  
  // Logout function
  const logout = () => {
    authService.logout();
    setUser(null);
    setIsAuthenticated(false);
  };
  
  return (
    <AuthContext.Provider value={{ user, isAuthenticated, login, signup, logout, checkAndRefreshToken }}>
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