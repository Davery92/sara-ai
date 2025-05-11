import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authService } from '../services/api';
import { jwtDecode } from 'jwt-decode';

interface User {
  username: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  token: string | null;
  login: (username: string, password: string) => Promise<void>;
  signup: (username: string, password: string) => Promise<void>;
  logout: () => void;
  checkAndRefreshToken: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{children: ReactNode}> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [token, setToken] = useState<string | null>(null);
  
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
    const storedToken = localStorage.getItem('accessToken');
    if (!storedToken) {
      setUser(null);
      setIsAuthenticated(false);
      setToken(null);
      return;
    }
    
    try {
      const decoded: any = jwtDecode(storedToken);
      
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
            setToken(newToken);
          }
        } catch (refreshError) {
          console.error('Failed to refresh token:', refreshError);
          // Clear auth state if refresh fails
          authService.logout();
          setUser(null);
          setIsAuthenticated(false);
          setToken(null);
        }
      } else {
        // Token is still valid
        setUser({ username: decoded.sub });
        setIsAuthenticated(true);
        setToken(storedToken);
      }
    } catch (error) {
      console.error('Invalid token:', error);
      authService.logout();
      setUser(null);
      setIsAuthenticated(false);
      setToken(null);
    }
  };
  
  // Login function
  const login = async (username: string, password: string) => {
    try {
      await authService.login(username, password);
      const storedToken = localStorage.getItem('accessToken');
      if (storedToken) {
        const decoded: any = jwtDecode(storedToken);
        setUser({ username: decoded.sub });
        setIsAuthenticated(true);
        setToken(storedToken);
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
      const storedToken = localStorage.getItem('accessToken');
      if (storedToken) {
        const decoded: any = jwtDecode(storedToken);
        setUser({ username: decoded.sub });
        setIsAuthenticated(true);
        setToken(storedToken);
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
    setToken(null);
  };
  
  return (
    <AuthContext.Provider value={{ user, isAuthenticated, token, login, signup, logout, checkAndRefreshToken }}>
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