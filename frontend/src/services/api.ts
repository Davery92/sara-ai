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
  // Send a message to the queue endpoint
  sendMessage: async (text: string, roomId: string = 'default-room') => {
    const token = localStorage.getItem('accessToken');
    return await api.post('/v1/chat/queue', { 
      room_id: roomId,
      msg: text 
    }, {
      headers: {
        'Authorization': token ? `Bearer ${token}` : '',
      }
    });
  },

  // Send chat completion via WebSocket
  sendChatCompletion: async (messages: any[], onStream?: (chunk: any) => void) => {
    const token = localStorage.getItem('accessToken');
    if (!token) {
      throw new Error('No authentication token available');
    }

    // Extract user ID from JWT token
    let userId = null;
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(''));
      
      const payload = JSON.parse(jsonPayload);
      userId = payload.sub;
      console.log('Extracted user ID from token:', userId);
    } catch (e) {
      console.error('Failed to extract user ID from token:', e);
    }

    console.log("📤 Sending chat completion request:", { messages });
    
    // If there's a streaming callback, use streaming mode
    const streamMode = !!onStream;
    
    try {
      if (streamMode) {
        console.log("Using streaming mode");
        
        // Create WebSocket connection
        const ws = new WebSocket(`ws://localhost:8000/v1/stream?token=${token}`);
        
        return new Promise((resolve, reject) => {
          ws.onopen = () => {
            console.log('WebSocket connected');
            // Send the chat request
            ws.send(JSON.stringify({
              model: 'qwen3:32b',
              messages,
              stream: true,
              max_tokens: 2000,
              room_id: 'default-room',
            }));
          };

          ws.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data);
              if (data.choices && data.choices[0]) {
                onStream?.(data);
              }
            } catch (e) {
              console.warn('Failed to parse WebSocket message:', e);
            }
          };

          ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            reject(error);
          };

          ws.onclose = () => {
            console.log('WebSocket closed');
            resolve({ data: { status: 'complete' } });
          };
        });
      } else {
        // Use non-streaming mode
        const response = await axios.post('http://localhost:8000/v1/chat/completions', 
          {
            model: 'qwen3:32b',
            messages,
            stream: false,
            max_tokens: 2000,
            user_id: userId,
            room_id: 'default-room',
          },
          {
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token}`,
            }
          }
        );
        
        console.log("📥 Received chat completion response:", response.data);
        return response;
      }
    } catch (error) {
      console.error("❌ Chat completion error:", error);
      throw error;
    }
  },
  
  // Set user persona preference
  setPersona: async (personaName: string) => {
    const token = localStorage.getItem('accessToken');
    
    try {
      const response = await axios.patch('http://localhost:8000/v1/persona', 
        { persona: personaName },
        {
          headers: {
            'Content-Type': 'application/json',
            'Authorization': token ? `Bearer ${token}` : '',
          }
        }
      );
      
      console.log("Set persona response:", response.data);
      return response.data;
    } catch (error) {
      console.error("Error setting persona:", error);
      throw error;
    }
  },
  
  // Get available personas
  getPersonas: async () => {
    const token = localStorage.getItem('accessToken');
    
    try {
      const response = await axios.get('http://localhost:8000/v1/persona/list',
        {
          headers: {
            'Authorization': token ? `Bearer ${token}` : '',
          }
        }
      );
      
      return response.data;
    } catch (error) {
      console.error("Error getting personas:", error);
      throw error;
    }
  }
};

export default api; 