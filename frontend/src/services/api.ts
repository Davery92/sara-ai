/**
 * src/api.ts  – unified helper layer
 *
 *  authService
 *    • signup / login / refresh / logout / getMe
 *
 *  chatService
 *    • send            – primary streaming call
 *    • sendMessage     – legacy wrapper → send()
 *    • getPersonas     – GET  /v1/persona/list
 *    • setPersona      – PATCH /v1/persona
 */

import axios from 'axios';

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
   * Primary helper: open /v1/stream WebSocket.
   * Resolves with the full assistant text; onChunk gives streaming updates.
   */
  send: (
    messages: any[],
    onChunk?: (chunk: string) => void,
    roomId = 'default-room'
  ) => new Promise<{ text: string }>((resolve, reject) => {
    const token = localStorage.getItem('accessToken');
    if (!token) return reject(new Error('No auth token'));

    const ws = new WebSocket(
      `ws://localhost:8000/v1/stream?token=${token}`
    );

    let full = '';

    ws.onopen = () =>
      ws.send(
        JSON.stringify({
          model: 'qwen3:32b',
          messages,
          stream: true,
          max_tokens: 2000,
          room_id: roomId,
        })
      );

    ws.onmessage = ({ data }) => {
      try {
        const chunk = JSON.parse(data as string);
        const delta = chunk.content ?? chunk.delta ?? '';
        if (delta) {
          full += delta;
          onChunk?.(delta);
        }
        if (chunk.finish_reason === 'stop' || chunk.done) ws.close();
      } catch {
        // plain-text token
        full += data as string;
        onChunk?.(data as string);
      }
    };

    ws.onerror = reject;
    ws.onclose = () => resolve({ text: full });
  }),

  /** legacy wrapper used by ChatInterface.tsx */
  sendMessage: async (text: string, roomId = 'default-room') => {
    await chatService.send(
      [{ role: 'user', content: text }],
      undefined,
      roomId
    );
    return { status: 'queued' };
  },

  /** GET available personas */
  getPersonas: async () => {
    const { data } = await api.get('/v1/persona/list');
    return data;                                // string[]
  },

  /** PATCH to set persona */
  setPersona: async (personaName: string) => {
    const { data } = await api.patch('/v1/persona', { persona: personaName });
    return data;                                // { status, persona }
  },
};

export default api;
