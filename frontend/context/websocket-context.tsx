'use client';

import React, { createContext, useContext, useState, useEffect, useRef, useCallback, ReactNode } from 'react';
import { useAuth } from '@/context/auth-context';

export type WebSocketStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

interface WebSocketContextType {
  wsInstance: WebSocket | null;
  wsStatus: WebSocketStatus;
  connect: (chatId: string) => void;
  disconnect: () => void;
  sendMessage: (message: any) => void;
  currentChatId: string | null;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export function useWebSocket() {
  const context = useContext(WebSocketContext);
  if (!context) throw new Error("useWebSocket must be used within a WebSocketProvider");
  return context;
}

// Custom event for WebSocket messages
export const WS_MESSAGE_EVENT = 'websocket-message';

// Define a custom event type
interface WebSocketMessageEvent extends CustomEvent {
  detail: any;
}

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const auth = useAuth(); // Get the whole auth context
  const [wsStatus, setWsStatus] = useState<WebSocketStatus>('idle');
  const [currentChatId, setCurrentChatId] = useState<string | null>(null); // Track the active chat ID for the WS
  const webSocketRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const connectDebounceRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectCountRef = useRef<number>(0);
  const connectionStateRef = useRef<'idle' | 'connecting' | 'connected' | 'disconnecting'>('idle');

  const MAX_RECONNECT_ATTEMPTS = 5;
  const PING_INTERVAL = 30000;
  const CONNECTION_DEBOUNCE = 300; // Slightly shorter debounce

  const dispatchMessageEvent = useCallback((data: any) => {
    if (typeof window === 'undefined') return;
    const event = new CustomEvent(WS_MESSAGE_EVENT, { detail: data });
    window.dispatchEvent(event);
  }, []);

  const startPingInterval = useCallback(() => {
    if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
    pingIntervalRef.current = setInterval(() => {
      if (webSocketRef.current?.readyState === WebSocket.OPEN) {
        webSocketRef.current.send('');
        console.log('[WSCtx] Sent WebSocket keepalive ping');
      }
    }, PING_INTERVAL);
  }, []);

  const cleanup = useCallback((calledFrom?: string) => {
    console.log(`[WSCtx] cleanup called from: ${calledFrom || 'unknown'}. Current state: ${connectionStateRef.current}, WS ref: ${webSocketRef.current ? webSocketRef.current.readyState : 'null'}`);
    
    if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
    pingIntervalRef.current = null;
    if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    reconnectTimeoutRef.current = null;
    if (connectDebounceRef.current) clearTimeout(connectDebounceRef.current);
    connectDebounceRef.current = null;

    if (webSocketRef.current) {
      connectionStateRef.current = 'disconnecting';
      console.log(`[WSCtx] Attempting to close WebSocket (readyState: ${webSocketRef.current.readyState})`);
      try {
        if (webSocketRef.current.readyState === WebSocket.OPEN || webSocketRef.current.readyState === WebSocket.CONNECTING) {
          webSocketRef.current.close();
        }
      } catch (e) { console.error('[WSCtx] Error closing WebSocket during cleanup:', e); }
      webSocketRef.current = null;
    }
    connectionStateRef.current = 'idle'; // Ensure state is reset
    // DO NOT setWsStatus here if called from connectToWebSocket's own cleanup
    // Only set if it's an explicit disconnect or a global auth change.
    if (calledFrom !== 'connectToWebSocket_pre_connect') {
        setWsStatus('disconnected');
    }
    // Do not clear currentChatId here; let the caller manage that.
  }, []);

  // Disconnect on unmount
  useEffect(() => {
    return () => cleanup('unmount');
  }, [cleanup]);

  // The actual connection function separated to allow for debouncing
  const connectToWebSocket = useCallback(async (chatIdToConnect: string) => { // Make it async
    console.log(`[WSCtx] connectToWebSocket called for chatId: ${chatIdToConnect}. Current state: ${connectionStateRef.current}, current WS ChatId: ${currentChatId}`);

    // Explicitly check auth status from context at the moment of call
    if (!auth.isAuthenticated) {
      console.warn('[WSCtx] connectToWebSocket: Auth check failed (isAuthenticated from context is false). Aborting.');
      setWsStatus('error'); // Or 'disconnected' / 'idle'
      return;
    }

    // Get a fresh access token for the WebSocket URL
    const tokenForWsUrl = await auth.getFreshAccessToken();

    if (!tokenForWsUrl) {
      console.warn('[WSCtx] connectToWebSocket: Failed to get a fresh access token for WS. Aborting.');
      setWsStatus('error');
      return;
    }
    console.log(`[WSCtx] Using fresh accessToken for WS: ${tokenForWsUrl.substring(0,10)}...`);
    
    // If already connected to the *same* chat ID, do nothing.
    if (connectionStateRef.current === 'connected' && webSocketRef.current && currentChatId === chatIdToConnect) {
        console.log(`[WSCtx] Already connected to ${chatIdToConnect}. Skipping.`);
        setWsStatus('connected'); // Ensure status reflects this
        return;
    }

    // If trying to connect to a different chat ID, or if not connected/connecting
    // always clean up previous before starting new.
    if (currentChatId !== chatIdToConnect || connectionStateRef.current !== 'connecting') {
        console.log(`[WSCtx] Mismatch or not connecting. currentChatId: ${currentChatId}, requested: ${chatIdToConnect}, state: ${connectionStateRef.current}. Cleaning up old connection.`);
        cleanup('connectToWebSocket_pre_connect');
    }
    
    setCurrentChatId(chatIdToConnect);
    connectionStateRef.current = 'connecting';
    setWsStatus('connecting');
    
    // ... (rest of your connection throttling logic if any, using lastConnectionAttemptRef) ...
    
    const wsBaseUrlFromEnv = process.env.NEXT_PUBLIC_BACKEND_WS_URL; // e.g., "ws://localhost:8000/v1/stream"
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let wsHostAndPath: string;

    if (wsBaseUrlFromEnv && (wsBaseUrlFromEnv.startsWith('ws://') || wsBaseUrlFromEnv.startsWith('wss://'))) {
        // If NEXT_PUBLIC_BACKEND_WS_URL is a full URL like "ws://localhost:8000/v1/stream"
        // We need to replace 'localhost' with the current window.location.hostname IF it's not localhost itself,
        // but keep the port and path from the env var.
        const parsedEnvUrl = new URL(wsBaseUrlFromEnv);
        const envHostname = parsedEnvUrl.hostname;
        const envPort = parsedEnvUrl.port || (parsedEnvUrl.protocol === 'wss:' ? '443' : '80');
        const envPath = parsedEnvUrl.pathname;

        // Use window.location.hostname if not trying to connect to 'localhost' or '127.0.0.1'
        // This allows using the host IP when NEXT_PUBLIC_BACKEND_WS_URL is set to localhost.
        const targetHostname = (envHostname === 'localhost' || envHostname === '127.0.0.1') ? window.location.hostname : envHostname;
        
        wsHostAndPath = `${targetHostname}:${envPort}${envPath}`;
        console.log(`[WSCtx] Constructed WS host and path from NEXT_PUBLIC_BACKEND_WS_URL: ${wsHostAndPath}`);
    } else {
        // Fallback if NEXT_PUBLIC_BACKEND_WS_URL is just a path like "/v1/stream" or not set
        const hostname = window.location.hostname;
        const backendPort = '8000'; // Always use the backend's exposed port
        const defaultPath = '/v1/stream'; // Default path
        const path = wsBaseUrlFromEnv && wsBaseUrlFromEnv.startsWith('/') ? wsBaseUrlFromEnv : defaultPath;
        wsHostAndPath = `${hostname}:${backendPort}${path}`;
        console.log(`[WSCtx] Constructed WS host and path using fallback: ${wsHostAndPath}`);
    }
    
    const wsUrl = `${scheme}//${wsHostAndPath}?token=${encodeURIComponent(tokenForWsUrl)}`;
    console.log('[WSCtx] Final WebSocket URL:', wsUrl);

    try {
      const ws = new WebSocket(wsUrl);
      webSocketRef.current = ws;

      const connectionTimeout = setTimeout(() => {
        if (connectionStateRef.current === 'connecting') {
          console.error('[WSCtx] WebSocket connection attempt timed out.');
          ws.close(); // This will trigger onclose
        }
      }, 10000); // 10-second timeout

      ws.onopen = () => {
        clearTimeout(connectionTimeout);
        console.log('[WSCtx] WebSocket connected successfully to:', wsUrl);
        connectionStateRef.current = 'connected';
        setWsStatus('connected');
        reconnectCountRef.current = 0;
        startPingInterval();
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data as string);
          dispatchMessageEvent(data);
        } catch (error) {
          console.error('[WSCtx] Error parsing WebSocket message:', error);
        }
      };
    
      ws.onerror = (error) => {
        clearTimeout(connectionTimeout);
        console.error('[WSCtx] WebSocket error:', error);
        // Don't change connectionStateRef here, let onclose handle it.
        setWsStatus('error');
      };

      ws.onclose = (event) => {
        clearTimeout(connectionTimeout);
        console.log(`[WSCtx] WebSocket closed for ${chatIdToConnect}: Code ${event.code}, Reason: ${event.reason}, Clean: ${event.wasClean}. Current state: ${connectionStateRef.current}`);
        
        if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;

        const previousState = connectionStateRef.current;
        connectionStateRef.current = 'idle'; // Reset state

        if (previousState === 'disconnecting') { // Intentional disconnect
          console.log('[WSCtx] WebSocket closed intentionally.');
          setWsStatus('disconnected');
        } else if (event.code === 1000 || event.wasClean) { // Clean close by server or client
          console.log('[WSCtx] WebSocket closed cleanly.');
          setWsStatus('disconnected');
        } else { // Abnormal close, attempt reconnect
          setWsStatus('error');
          if (reconnectCountRef.current < MAX_RECONNECT_ATTEMPTS) {
            reconnectCountRef.current++;
            const delay = Math.min(1000 * Math.pow(2, reconnectCountRef.current -1), 30000);
            console.log(`[WSCtx] Attempting reconnect ${reconnectCountRef.current}/${MAX_RECONNECT_ATTEMPTS} in ${delay}ms for ${chatIdToConnect}`);
            if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = setTimeout(() => connectToWebSocket(chatIdToConnect), delay);
          } else {
            console.error(`[WSCtx] Max reconnect attempts reached for ${chatIdToConnect}.`);
          }
        }
      };
    } catch (e) {
        console.error('[WSCtx] Error instantiating WebSocket:', e);
        connectionStateRef.current = 'idle';
        setWsStatus('error');
    }
  }, [auth, cleanup, dispatchMessageEvent, startPingInterval, currentChatId]); // auth is now a dependency

  const connect = useCallback((chatIdToConnect: string) => {
    console.log(`[WSCtx] connect function called for chatId: ${chatIdToConnect}. Debouncing.`);
    if (connectDebounceRef.current) {
      clearTimeout(connectDebounceRef.current);
    }
    connectDebounceRef.current = setTimeout(() => {
      console.log(`[WSCtx] Debounced connectToWebSocket executing for ${chatIdToConnect}`);
      connectToWebSocket(chatIdToConnect);
    }, CONNECTION_DEBOUNCE);
  }, [connectToWebSocket]);

  const disconnect = useCallback(() => {
    console.log('[WSCtx] disconnect function called explicitly.');
    cleanup('disconnect_explicit');
    setCurrentChatId(null); // Clear the chat ID on explicit disconnect
    setWsStatus('disconnected');
  }, [cleanup]);

  const sendMessage = useCallback((message: any) => {
    if (!webSocketRef.current || webSocketRef.current.readyState !== WebSocket.OPEN) {
      console.error('[WSCtx] sendMessage: WebSocket not connected or not for current chat. Attempting to connect.');
      if (currentChatId) connectToWebSocket(currentChatId); // Re-attempt connection for the current chat
      return;
    }
    webSocketRef.current.send(typeof message === 'string' ? message : JSON.stringify(message));
  }, [currentChatId, connectToWebSocket]);

  // Effect to handle auth changes
  useEffect(() => {
    console.log(`[WSCtx Provider useEffect] Auth state changed: isAuthenticated=${auth.isAuthenticated}, authIsLoading=${auth.isLoading}`);
    if (!auth.isLoading) { // Only react once auth loading is done
        if (auth.isAuthenticated) {
            // If authenticated and there's a currentChatId, ensure connection is active or try to connect.
            if (currentChatId && (wsStatus === 'disconnected' || wsStatus === 'error' || wsStatus === 'idle')) {
                 console.log(`[WSCtx Provider useEffect] Auth ready, WS not connected for ${currentChatId}. Triggering connect.`);
                 connect(currentChatId);
            } else if (currentChatId && wsStatus === 'connected'){
                 console.log(`[WSCtx Provider useEffect] Auth ready, WS already connected for ${currentChatId}.`);
            } else if (!currentChatId) {
                 console.log(`[WSCtx Provider useEffect] Auth ready, but no currentChatId set to connect to.`);
            }
        } else {
            // If not authenticated, ensure any existing WebSocket is disconnected.
            if (webSocketRef.current) {
                console.log("[WSCtx Provider useEffect] Auth is false. Disconnecting WebSocket.");
                disconnect();
            }
        }
    }
  }, [auth.isAuthenticated, auth.isLoading, currentChatId, wsStatus, connect, disconnect]);

  return (
    <WebSocketContext.Provider value={{ wsInstance: webSocketRef.current, wsStatus, connect, disconnect, sendMessage, currentChatId }}>
      {children}
    </WebSocketContext.Provider>
  );
} 