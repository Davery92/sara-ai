/**
 * src/api.ts  – unified WebSocket + REST API client
 *
 *  authService
 *    • signup / login / refresh / logout / getMe
 *
 *  chatService
 *    • sendMessage     – primary streaming call
 *    • getPersonas     – GET  /v1/persona/list
 *    • setPersona      – PATCH /v1/persona
 * 
 *  healthService
 *    • checkServices   - GET /health/all
 */

import axios from 'axios';

/* ───────────────────────────
   Logging utility
   ─────────────────────────── */
const logEvent = (type: string, message: string, details = {}) => {
  console.log(`[${type}]`, message, details);
};

/* ───────────────────────────
   Axios instance w/ auth token
   ─────────────────────────── */
const api = axios.create({
  baseURL: 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const t = localStorage.getItem('accessToken');
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const refreshToken = localStorage.getItem('refreshToken');
        if (!refreshToken) throw new Error('No refresh token available');
        const { data } = await axios.post('http://localhost:8000/auth/refresh', { refresh_token: refreshToken });
        storeTokens(data);
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        return axios(originalRequest);
      } catch (err) {
        console.error('Token refresh failed:', err);
        localStorage.removeItem('accessToken');
        localStorage.removeItem('refreshToken');
        return Promise.reject(err);
      }
    }
    return Promise.reject(error);
  }
);

/* ──────────  Auth  ───────── */
export const authService = {
  signup: async (username: string, password: string) => {
    const { data } = await api.post('/auth/signup', { username, password });
    storeTokens(data);
    return data;
  },

  login: async (username: string, password: string) => {
    const { data } = await api.post('/auth/login', { username, password });
    storeTokens(data);
    return data;
  },

  refreshToken: async () => {
    const refresh = localStorage.getItem('refreshToken');
    const { data } = await api.post('/auth/refresh', { refresh_token: refresh });
    storeTokens(data);
    return data;
  },

  logout: () => {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
  },

  getMe: () => api.get('/auth/me'),
};

const storeTokens = (d: any) => {
  if (d?.access_token) {
    localStorage.setItem('accessToken',  d.access_token);
    localStorage.setItem('refreshToken', d.refresh_token);
  }
};

/* ──────────  Chat  ───────── */
export const chatService = {
  /**
   * Open /v1/stream WebSocket.
   * Resolves with full text; emits partials to onChunk.
   */
  sendMessage: (
    messages: any[],
    onChunk?: (chunk: string) => void,
    onError?: (error: string) => void,
    roomId = 'default-room'
  ) => new Promise<{ text: string, success: boolean }>((resolve, reject) => {
    const token = localStorage.getItem('accessToken');
    if (!token) {
      const error = 'No auth token';
      logEvent('ERROR', error);
      onError?.(error);
      return reject(new Error(error));
    }

    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.hostname;
    const ws = new WebSocket(`${scheme}://${host}:8000/v1/stream?token=${token}`);

    let full = '';
    let success = false;
    let connectionTimeout = setTimeout(() => {
      ws.close();
      const error = 'Connection timeout after 10s';
      logEvent('ERROR', error, { roomId });
      onError?.(error);
      resolve({ text: '', success: false });
    }, 10000);

    ws.onopen = () => {
      logEvent('WS', 'Connection opened', { roomId });
      clearTimeout(connectionTimeout);
      ws.send(JSON.stringify({
        model: 'qwen3:32b',
        messages,
        stream: true,
        max_tokens: 2000,
        room_id: roomId,
      }));
    };

    ws.onmessage = ({ data }) => {
      let msg;
      try {
        msg = JSON.parse(data);
      } catch {
        return;  // not JSON, just skip
      }
    
      const choice = msg.choices?.[0] || {};
      const delta = choice.delta || {};
      const finish = choice.finish_reason;
    
      // ✅ Only emit real content chunks
      if (typeof delta.content === "string") {
        full += delta.content;
        onChunk?.(delta.content);
      }
    
      // ✅ Stop signal
      if (finish === "stop") {
        success = true;
        ws.close();
      }
    };
    

    ws.onerror = (event) => {
      const errorMsg = 'WebSocket error occurred';
      logEvent('ERROR', errorMsg, { event });
      onError?.(errorMsg);
      reject(new Error(errorMsg));
    };

    ws.onclose = (event) => {
      clearTimeout(connectionTimeout);
      logEvent('WS', 'Connection closed', { code: event.code, clean: event.wasClean, full });
      if (!success && !event.wasClean) {
        const errorMsg = `Connection closed abnormally (code: ${event.code})`;
        onError?.(errorMsg);
      }
      resolve({ text: full, success });
    };
  }),

  getPersonas: async () => {
    logEvent('PERSONA', 'Getting personas');
    const { data } = await api.get('/v1/persona/list');
    return data;
  },

  setPersona: async (personaName: string) => {
    logEvent('PERSONA', 'Setting persona', { name: personaName });
    const { data } = await api.patch('/v1/persona', { persona: personaName });
    return data;
  },
};

/* ───────── Health Monitoring ───────── */
export const healthService = {
  checkServices: async () => {
    logEvent('HEALTH', 'Checking service health');
    try {
      const { data } = await api.get('/health/all');
      logEvent('HEALTH', 'Health check completed', data);
      return data;
    } catch (error) {
      logEvent('ERROR', 'Health check failed', { error });
      return {
        gateway: false,
        nats: false,
        llm_proxy: false,
        ollama: false,
      };
    }
  },
};

export default api;
