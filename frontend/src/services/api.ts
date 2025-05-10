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
  sendChatCompletion: async (messages: any[], onStream?: (chunk: any) => void) => {
    // Use the full URL path with domain to bypass proxy issues
    // Explicitly include the authorization header for absolute URLs
    const token = localStorage.getItem('accessToken');
    
    // Extract user ID from JWT token
    let userId = null;
    if (token) {
      try {
        // Simple JWT extraction (not full validation)
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => {
          return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        
        const payload = JSON.parse(jsonPayload);
        userId = payload.sub; // JWT subject field contains username/user_id
        console.log('Extracted user ID from token:', userId);
      } catch (e) {
        console.error('Failed to extract user ID from token:', e);
      }
    }
    
    console.log("📤 Sending chat completion request:", { messages });
    
    // If there's a streaming callback, use streaming mode
    const streamMode = !!onStream;
    
    try {
      if (streamMode) {
        console.log("Using streaming mode");
        
        // Simple, direct approach for handling Server-Sent Events
        const response = await fetch('http://localhost:8000/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': token ? `Bearer ${token}` : '',
          },
          body: JSON.stringify({
            model: 'qwen3:32b',
            messages,
            stream: true,
            max_tokens: 2000,
            // Include user_id but only for backend logging/routing
            room_id: 'default-room',
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('ReadableStream not supported');
        }
        
        const decoder = new TextDecoder();
        let partialLine = '';
        
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          
          // Decode the value to a string
          const text = decoder.decode(value, { stream: true });
          
          // Process each chunk to handle SSE format - lines that start with "data: "
          const lines = (partialLine + text).split('\n');
          partialLine = lines.pop() || ''; // Save any partial line for next time
          
          for (const line of lines) {
            const trimmedLine = line.trim();
            
            // Skip empty lines or DONE messages
            if (trimmedLine === '' || trimmedLine === 'data: [DONE]') {
              continue;
            }
            
            // Extract the JSON data
            if (trimmedLine.startsWith('data: ')) {
              try {
                const jsonStr = trimmedLine.slice(6); // Remove "data: " prefix
                const jsonData = JSON.parse(jsonStr);
                onStream(jsonData);
              } catch (e) {
                console.warn('Failed to parse JSON from SSE:', trimmedLine, e);
              }
            }
          }
        }
        
        return { data: { status: 'complete' } };
      } else {
        // Use non-streaming mode
        const response = await axios.post('http://localhost:8000/v1/chat/completions', 
          {
            model: 'qwen3:32b',
            messages,
            stream: false,
            max_tokens: 2000,
            // Include user_id for persona selection on backend
            user_id: userId,
            room_id: 'default-room', // Use a default room ID for memory context
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