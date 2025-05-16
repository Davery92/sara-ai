'use client';

import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
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

const WebSocketContext = createContext<WebSocketContextType>({
  wsInstance: null,
  wsStatus: 'idle',
  connect: () => {},
  disconnect: () => {},
  sendMessage: () => {},
  currentChatId: null,
});

export function useWebSocket() {
  return useContext(WebSocketContext);
}

// Custom event for WebSocket messages
export const WS_MESSAGE_EVENT = 'websocket-message';

// Define a custom event type
interface WebSocketMessageEvent extends CustomEvent {
  detail: any;
}

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const { accessToken, isAuthenticated } = useAuth();
  const [wsStatus, setWsStatus] = useState<WebSocketStatus>('idle');
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const webSocketRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const connectDebounceRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectCountRef = useRef<number>(0);
  const lastConnectionAttemptRef = useRef<number>(0);
  const connectionStateRef = useRef<'idle' | 'connecting' | 'connected' | 'disconnecting'>('idle');
  const MAX_RECONNECT_ATTEMPTS = 5;
  const PING_INTERVAL = 30000; // 30 seconds
  const CONNECTION_DEBOUNCE = 500; // Debounce connections by 500ms

  // Function to clean up websocket resources
  const cleanup = useCallback(() => {
    console.log('Cleaning up WebSocket resources');

    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (connectDebounceRef.current) {
      clearTimeout(connectDebounceRef.current);
      connectDebounceRef.current = null;
    }

    if (webSocketRef.current) {
      console.log('Closing existing WebSocket connection with state:', connectionStateRef.current);
      connectionStateRef.current = 'disconnecting';
      
      try {
        if (webSocketRef.current.readyState === WebSocket.OPEN || 
            webSocketRef.current.readyState === WebSocket.CONNECTING) {
          webSocketRef.current.close();
        }
      } catch (e) {
        console.error('Error closing WebSocket:', e);
      }
      
      webSocketRef.current = null;
      connectionStateRef.current = 'idle';
    }
  }, []);

  // Disconnect on unmount
  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  // Start ping interval to keep connection alive
  const startPingInterval = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
    }

    pingIntervalRef.current = setInterval(() => {
      if (webSocketRef.current?.readyState === WebSocket.OPEN) {
        // Send empty message as heartbeat
        webSocketRef.current.send('');
        console.log('Sent WebSocket keepalive ping');
      }
    }, PING_INTERVAL);
  }, []);

  // Helper to dispatch WebSocket message events
  const dispatchMessageEvent = useCallback((data: any) => {
    if (typeof window === 'undefined') return;

    const event = new CustomEvent(WS_MESSAGE_EVENT, { 
      detail: data 
    });
    window.dispatchEvent(event);
  }, []);

  // The actual connection function separated to allow for debouncing
  const connectToWebSocket = useCallback((chatId: string) => {
    if (!isAuthenticated || !accessToken) {
      console.warn('Cannot connect to WebSocket: not authenticated');
      setWsStatus('error');
      return;
    }

    // Check if we're already connected or connecting to the same room
    if (
      connectionStateRef.current !== 'idle' && 
      webSocketRef.current && 
      currentChatId === chatId
    ) {
      console.log(`Already ${connectionStateRef.current} to chat room ${chatId}, skipping connection`);
      return;
    }

    // Enforce minimum time between connection attempts
    const now = Date.now();
    if (now - lastConnectionAttemptRef.current < 1000) {
      console.log('Connection attempt too frequent, throttling');
      
      // Only set a new timeout if we're not already waiting
      if (!connectDebounceRef.current) {
        connectDebounceRef.current = setTimeout(() => {
          connectToWebSocket(chatId);
        }, 1000);
      }
      return;
    }
    
    lastConnectionAttemptRef.current = now;

    // Clean up any existing connection
    cleanup();
    
    // Update current chat ID and state
    setCurrentChatId(chatId);
    connectionStateRef.current = 'connecting';
    setWsStatus('connecting');

    // Construct WebSocket URL
    try {
      const wsBaseUrl = process.env.NEXT_PUBLIC_BACKEND_WS_URL || '/api/stream';
      const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const hostname = window.location.hostname;
      const port = '8000'; // Use port 8000 for backend
      const host = `${hostname}:${port}`;
      const path = wsBaseUrl.startsWith('/') ? wsBaseUrl : `/${wsBaseUrl}`;
      const wsUrl = `${scheme}//${host}${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(accessToken)}`;

      console.log('Connecting to WebSocket:', wsUrl);

      // Create WebSocket connection
      const ws = new WebSocket(wsUrl);
      webSocketRef.current = ws;

      // Set a connection timeout
      const connectionTimeout = setTimeout(() => {
        if (connectionStateRef.current === 'connecting') {
          console.log('WebSocket connection timeout after 5 seconds');
          connectionStateRef.current = 'disconnecting';
          
          if (webSocketRef.current) {
            webSocketRef.current.close();
          }
          
          webSocketRef.current = null;
          connectionStateRef.current = 'idle';
          setWsStatus('error');
        }
      }, 5000);

      ws.onopen = () => {
        clearTimeout(connectionTimeout);
        console.log('WebSocket connected successfully to:', wsUrl);
        connectionStateRef.current = 'connected';
        setWsStatus('connected');
        
        // Reset reconnect attempts on successful connection
        reconnectCountRef.current = 0;
        
        // Start the keepalive pings
        startPingInterval();
      };

      ws.onmessage = (event) => {
        // Handle incoming messages - dispatch custom event
        try {
          const data = JSON.parse(event.data);
          console.log('WebSocket message received');
          
          // Dispatch the message event
          dispatchMessageEvent(data);
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      ws.onerror = (error) => {
        clearTimeout(connectionTimeout);
        console.error('WebSocket error:', error);
        
        // Only change state if we're still in connecting/connected state
        if (connectionStateRef.current === 'connecting' || connectionStateRef.current === 'connected') {
          connectionStateRef.current = 'idle';
          setWsStatus('error');
        }
      };

      ws.onclose = (event) => {
        clearTimeout(connectionTimeout);
        console.log(`WebSocket closed: ${event.code} ${event.reason}`);
        
        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        // Only handle reconnection if we weren't already disconnecting intentionally
        if (connectionStateRef.current !== 'disconnecting') {
          connectionStateRef.current = 'idle';
          
          if (event.wasClean) {
            setWsStatus('disconnected');
          } else {
            setWsStatus('error');
            
            // Attempt reconnection if not intentionally closed
            if (reconnectCountRef.current < MAX_RECONNECT_ATTEMPTS) {
              const delay = Math.min(1000 * Math.pow(2, reconnectCountRef.current), 30000);
              reconnectCountRef.current++;
              
              console.log(`Attempting to reconnect in ${delay}ms. Attempt ${reconnectCountRef.current} of ${MAX_RECONNECT_ATTEMPTS}`);
              
              reconnectTimeoutRef.current = setTimeout(() => {
                if (chatId) {
                  connectToWebSocket(chatId);
                }
              }, delay);
            }
          }
        } else {
          // If we were intentionally disconnecting, just update the state
          connectionStateRef.current = 'idle';
          setWsStatus('disconnected');
        }
      };
    } catch (error) {
      console.error('Error creating WebSocket:', error);
      connectionStateRef.current = 'idle';
      setWsStatus('error');
    }
  }, [accessToken, cleanup, dispatchMessageEvent, isAuthenticated, startPingInterval, currentChatId]);

  // Connect to WebSocket
  const connect = useCallback((chatId: string) => {
    // Debounce connection requests to prevent rapid reconnections
    if (connectDebounceRef.current) {
      clearTimeout(connectDebounceRef.current);
    }

    // Store the requested chatId for the debounced connection
    connectDebounceRef.current = setTimeout(() => {
      connectToWebSocket(chatId);
    }, CONNECTION_DEBOUNCE);
  }, [connectToWebSocket]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    console.log('Disconnecting WebSocket');
    cleanup();
    setCurrentChatId(null);
    setWsStatus('disconnected');
  }, [cleanup]);

  // Send message over WebSocket
  const sendMessage = useCallback((message: any) => {
    if (!webSocketRef.current || webSocketRef.current.readyState !== WebSocket.OPEN) {
      console.error('Cannot send message: WebSocket not connected');
      return;
    }

    try {
      webSocketRef.current.send(typeof message === 'string' ? message : JSON.stringify(message));
    } catch (error) {
      console.error('Error sending message:', error);
    }
  }, []);

  const contextValue: WebSocketContextType = {
    wsInstance: webSocketRef.current,
    wsStatus,
    connect,
    disconnect,
    sendMessage,
    currentChatId,
  };

  return (
    <WebSocketContext.Provider value={contextValue}>
      {children}
    </WebSocketContext.Provider>
  );
} 