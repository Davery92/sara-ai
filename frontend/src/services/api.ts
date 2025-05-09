import axios from 'axios';

// Create an axios instance with base URL
// No need for base URL since we're using the proxy
const api = axios.create({
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add a request interceptor to include auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('accessToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add a response interceptor to handle token refresh
api.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    
    // If the error is 401 (Unauthorized) and we haven't already tried to refresh
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true; // Mark that we're trying to refresh
      
      try {
        // Try to refresh the token
        const refreshToken = localStorage.getItem('refreshToken');
        if (!refreshToken) {
          throw new Error('No refresh token available');
        }
        
        const response = await axios.post('http://localhost:8000/auth/refresh', { 
          refresh_token: refreshToken 
        });
        
        // Store the new tokens
        const { access_token, refresh_token } = response.data;
        localStorage.setItem('accessToken', access_token);
        localStorage.setItem('refreshToken', refresh_token);
        
        // Retry the original request with the new token
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return axios(originalRequest);
      } catch (refreshError) {
        console.error('Token refresh failed:', refreshError);
        localStorage.removeItem('accessToken');
        localStorage.removeItem('refreshToken');
        // Redirect to login page or handle auth failure
        return Promise.reject(refreshError);
      }
    }
    
    return Promise.reject(error);
  }
);

// Authentication service
export const authService = {
  // Register a new user
  signup: async (username: string, password: string) => {
    // Use the full URL path with domain to bypass proxy issues
    const response = await api.post('http://localhost:8000/auth/signup', { username, password });
    if (response.data.access_token) {
      localStorage.setItem('accessToken', response.data.access_token);
      localStorage.setItem('refreshToken', response.data.refresh_token);
    }
    return response.data;
  },

  // Login
  login: async (username: string, password: string) => {
    // Use the full URL path with domain to bypass proxy issues
    const response = await api.post('http://localhost:8000/auth/login', { username, password });
    if (response.data.access_token) {
      localStorage.setItem('accessToken', response.data.access_token);
      localStorage.setItem('refreshToken', response.data.refresh_token);
    }
    return response.data;
  },

  // Logout
  logout: () => {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
  },

  // Get current user
  getMe: async () => {
    return await api.get('/auth/me');
  },
  
  // Refresh token
  refreshToken: async () => {
    const refreshToken = localStorage.getItem('refreshToken');
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }
    
    const response = await api.post('http://localhost:8000/auth/refresh', { 
      refresh_token: refreshToken 
    });
    
    if (response.data.access_token) {
      localStorage.setItem('accessToken', response.data.access_token);
      localStorage.setItem('refreshToken', response.data.refresh_token);
    }
    
    return response.data;
  },
  
  // Force login with existing credentials
  forceRefresh: async () => {
    try {
      // Try login with David account (for development purposes only)
      const response = await axios.post('http://localhost:8000/auth/login', { 
        username: 'David', 
        password: 'password' 
      });
      
      if (response.data.access_token) {
        localStorage.setItem('accessToken', response.data.access_token);
        localStorage.setItem('refreshToken', response.data.refresh_token);
        console.log('Successfully refreshed auth tokens');
        return true;
      }
      return false;
    } catch (error) {
      console.error('Failed to force refresh tokens:', error);
      return false;
    }
  }
};

// Chat service
export const chatService = {
  // Send a message
  sendMessage: async (text: string) => {
    return await api.post('/messages/', { text });
  },

  // Send chat completion
  sendChatCompletion: async (messages: any[]) => {
    // Use the full URL path with domain to bypass proxy issues
    // Explicitly include the authorization header for absolute URLs
    const token = localStorage.getItem('accessToken');
    
    console.log("📤 Sending chat completion request:", { messages });
    
    try {
      const response = await axios.post('http://localhost:8000/v1/chat/completions', 
        {
          model: 'qwen3:32b',  // Use the qwen3:32b model
          messages,
          stream: false,
          max_tokens: 2000,           // Set a reasonable limit
        },
        {
          headers: {
            'Content-Type': 'application/json',
            'Authorization': token ? `Bearer ${token}` : '',
          }
        }
      );
      
      console.log("📥 Received chat completion response:", response.data);
      return response;
    } catch (error) {
      console.error("❌ Chat completion error:", error);
      throw error;
    }
  },
};

export default api; 