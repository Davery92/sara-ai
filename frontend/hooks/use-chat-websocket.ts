'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/context/auth-context';
import type { UIMessage } from 'ai'; // Using UIMessage type from Vercel AI SDK for convenience
import { generateUUID } from '@/lib/utils';

// At the top of the file, add this interface to declare the global type
declare global {
  interface Window {
    __wsConnectionCount?: number;
  }
}

// Define the structure of the message payload to send to the WebSocket
interface WebSocketSendMessage {
  room_id: string; // chat_id from the frontend
  msg: string;     // User's message text
  model?: string;   // Optional: if model selection is supported
  // messages?: UIMessage[]; // Alternative: send the whole message history
}

// Define the structure of an incoming WebSocket message chunk (based on provided backend example)
// Example: {"choices":[{"delta":{"content":"..."}}]}
interface OllamaStreamChunk {
  choices?: Array<{
    delta?: {
      content?: string;
    };
    finish_reason?: string;
  }>;
  model?: string; // Ollama might also send the model name
  created_at?: string; // and other fields
  done?: boolean; // Ollama sometimes uses 'done' instead of finish_reason
  // Add other potential fields from your specific backend stream if necessary
  error?: string; // For error messages from the WebSocket
}

export type WebSocketStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

interface UseChatWebSocketOptions {
  chatId: string;
  initialMessages?: UIMessage[];
  modelId?: string;
  onMessagesUpdate?: (messages: UIMessage[]) => void; // Renamed for clarity
  onStatusChange?: (status: WebSocketStatus) => void;
  onError?: (error: string) => void;
  onMessage?: (message: any) => void; // Add handler for artifact messages
}

export function useChatWebSocket({
  chatId,
  initialMessages = [],
  modelId,
  onMessagesUpdate, // Renamed
  onStatusChange,
  onError,
  onMessage, // New handler for artifact messages
}: UseChatWebSocketOptions) {
  const { accessToken, isAuthenticated, isLoading: authIsLoading } = useAuth();
  const [messages, setMessages] = useState<UIMessage[]>(initialMessages);
  const [wsStatus, setWsStatus] = useState<WebSocketStatus>('idle');
  const webSocketRef = useRef<WebSocket | null>(null);
  const currentAssistantMessageIdRef = useRef<string | null>(null);
  
  // Add reconnection tracking
  const reconnectAttemptRef = useRef<number>(0);
  const maxReconnectAttempts = 5;
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  
  // Add keepalive ping reference
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const PING_INTERVAL = 30000; // 30 seconds
  
  // Track if we've encountered a resource limit error
  const resourceLimitErrorRef = useRef<boolean>(false);
  const connectionAttemptTimeRef = useRef<number>(0);
  
  // Track connection state to prevent redundant connections
  const connectionStateRef = useRef<'idle' | 'connecting' | 'connected' | 'disconnecting'>('idle');
  const isReconnectingRef = useRef<boolean>(false);
  
  // Static connection counter to limit number of connections
  // This helps prevent "Insufficient resources" errors
  const MAX_CONNECTIONS = 3;
  const RETRY_AFTER_MS = 2000;
  
  // Use a static connection counter (shared across hook instances)
  if (typeof window !== 'undefined') {
    // Initialize static counter if it doesn't exist
    if (!window.__wsConnectionCount) {
      window.__wsConnectionCount = 0;
    }
  }

  const updateStatus = useCallback((status: WebSocketStatus) => {
    setWsStatus(status);
    onStatusChange?.(status);
  }, [onStatusChange]);
  
  // Function to reset all connection state
  const resetConnectionState = useCallback(() => {
    console.log('Resetting WebSocket connection state');
    
    // Clear all timeouts and intervals
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
    
    // Reset state flags
    connectionStateRef.current = 'idle';
    isReconnectingRef.current = false;
    reconnectAttemptRef.current = 0;
    
    // Close any existing connection
    if (webSocketRef.current) {
      if (webSocketRef.current.readyState === WebSocket.OPEN || 
          webSocketRef.current.readyState === WebSocket.CONNECTING) {
        webSocketRef.current.close();
      }
      webSocketRef.current = null;
    }
  }, []);

  // Add a ping function to keep the connection alive
  const startPingInterval = useCallback(() => {
    // Clear any existing interval first
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
    }
    
    // Set up new ping interval
    pingIntervalRef.current = setInterval(() => {
      if (webSocketRef.current?.readyState === WebSocket.OPEN) {
        // Send an empty ping message
        // This will be ignored by the server as per the code in ws.py:
        // "ignore empty keep-alive frames some clients send"
        webSocketRef.current.send("");
        console.log("Sent WebSocket keepalive ping");
      }
    }, PING_INTERVAL);
  }, []);

  const reportError = useCallback((errorMsg: string) => {
    console.error('WebSocket Error:', errorMsg);
    onError?.(errorMsg);
    updateStatus('error');
  }, [onError, updateStatus]);

  useEffect(() => {
    // Initialize messages from initialMessages if they differ from current state (e.g. prop update)
    // This might be useful if parent component wants to reset/load chat history
    setMessages(initialMessages);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialMessages]);

  // Setup WebSocket connection
  const setupWebSocket = useCallback(() => {
    // Prevent redundant connection attempts
    if (connectionStateRef.current === 'connecting' || connectionStateRef.current === 'connected') {
      console.log(`WebSocket already ${connectionStateRef.current}, avoiding redundant connection`);
      return;
    }

    if (!chatId || !isAuthenticated || authIsLoading) {
      if (webSocketRef.current && webSocketRef.current.readyState !== WebSocket.CLOSED && webSocketRef.current.readyState !== WebSocket.CLOSING) {
        console.log('Closing WebSocket due to auth state change or missing chatId.');
        connectionStateRef.current = 'disconnecting';
        webSocketRef.current.close();
      }
      updateStatus(isAuthenticated && chatId ? 'idle' : 'disconnected');
      return;
    }

    if (!accessToken) {
        reportError('Access token not available for WebSocket connection.');
        return;
    }

    // Get WebSocket URL from environment variable
    const wsBaseUrl = process.env.NEXT_PUBLIC_BACKEND_WS_URL || '/api/stream';
    // Handle both absolute and relative URLs
    let wsUrl;
    let attemptedFallback = false;
    
    // Add a utility function to check if the server is available
    const checkBackendAvailability = async (host: string): Promise<boolean> => {
      try {
        // Use fetch to check if the server is responding (with a small timeout)
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000);
        
        const healthEndpoint = `${window.location.protocol}//${host}/health`;
        await fetch(healthEndpoint, { 
          signal: controller.signal,
          method: 'HEAD'
        });
        
        clearTimeout(timeoutId);
        return true;
      } catch (error) {
        console.log(`Backend at ${host} is not available:`, error);
        return false;
      }
    };

    const tryConnect = (url: string) => {
      // Prevent connection if already connecting or connected
      if (connectionStateRef.current === 'connecting' || connectionStateRef.current === 'connected') {
        console.log(`WebSocket already ${connectionStateRef.current}, skipping new connection attempt to ${url}`);
        return;
      }
      
      console.log('Attempting to connect to WebSocket URL:', url);
      connectionStateRef.current = 'connecting';
      updateStatus('connecting');
      
      if (webSocketRef.current) {
        connectionStateRef.current = 'disconnecting';
        webSocketRef.current.close();
        webSocketRef.current = null;
        connectionStateRef.current = 'idle';
      }
      
      // Check if we're at the connection limit
      const now = Date.now();
      if (window.__wsConnectionCount && window.__wsConnectionCount >= MAX_CONNECTIONS) {
        console.warn(`WebSocket connection limit reached (${MAX_CONNECTIONS}). Will retry in ${RETRY_AFTER_MS}ms.`);
        
        // Set a timeout to try again after a delay
        setTimeout(() => {
          console.log('Retrying WebSocket connection after delay...');
          connectionStateRef.current = 'idle';
          tryConnect(url);
        }, RETRY_AFTER_MS);
        return;
      }
      
      // Also enforce a minimum time between connection attempts to prevent rapid reconnections
      if (now - connectionAttemptTimeRef.current < 1000) {
        console.warn('Connection attempts too frequent, adding delay');
        setTimeout(() => {
          console.log('Retrying WebSocket connection after throttling delay...');
          connectionStateRef.current = 'idle';
          tryConnect(url);
        }, 1000);
        return;
      }
      
      connectionAttemptTimeRef.current = now;
      
      // Add connection timeout
      const connectionTimeoutRef = setTimeout(() => {
        if (webSocketRef.current && webSocketRef.current.readyState !== WebSocket.OPEN) {
          console.log('WebSocket connection timeout after 5 seconds');
          connectionStateRef.current = 'disconnecting';
          webSocketRef.current.close();
          connectionStateRef.current = 'idle';
          
          if (!attemptedFallback) {
            // Try fallback to port 8000 if connecting to any other port
            attemptedFallback = true;
            
            // Check if URL contains a port that's not 8000
            const urlObj = new URL(url);
            const currentPort = urlObj.port;
            
            if (currentPort !== '8000') {
              // Try port 8000 as fallback
              urlObj.port = '8000';
              const fallbackUrl = urlObj.toString();
              console.log(`Trying fallback WebSocket URL with port 8000: ${fallbackUrl}`);
              tryConnect(fallbackUrl);
              return;
            }
          }
          reportError('WebSocket connection timeout');
        }
      }, 5000);
      
      try {
        // Increment connection counter
        if (window.__wsConnectionCount !== undefined) {
          window.__wsConnectionCount++;
          console.log(`Active WebSocket connections: ${window.__wsConnectionCount}`);
        }
        
        const ws = new WebSocket(url);
        webSocketRef.current = ws;

        ws.onerror = (event) => {
          console.error('WebSocket connection error:', event);
          clearTimeout(connectionTimeoutRef);
          
          // Check if error message contains "Insufficient resources"
          const errorEvent = event as ErrorEvent;
          if (errorEvent.message && errorEvent.message.includes('Insufficient resources')) {
            resourceLimitErrorRef.current = true;
            console.warn('WebSocket connection failed due to insufficient resources. Will retry with backoff.');
            
            // Decrement connection counter
            if (window.__wsConnectionCount !== undefined) {
              window.__wsConnectionCount = Math.max(0, window.__wsConnectionCount - 1);
            }
            
            // Add a delay before retrying
            setTimeout(() => {
              console.log('Retrying WebSocket connection after resource limit error...');
              connectionStateRef.current = 'idle';
              tryConnect(url);
            }, 5000);
            return;
          }
          
          if (!attemptedFallback) {
            attemptedFallback = true;
            
            // Check if URL contains a port that's not 8000
            try {
              const urlObj = new URL(url);
              const currentPort = urlObj.port;
              
              if (currentPort !== '8000') {
                // Try port 8000 as fallback
                urlObj.port = '8000';
                const fallbackUrl = urlObj.toString();
                console.log(`Error occurred. Trying fallback WebSocket URL with port 8000: ${fallbackUrl}`);
                connectionStateRef.current = 'idle';
                tryConnect(fallbackUrl);
                return;
              }
            } catch (e) {
              console.error('Error parsing URL for fallback:', e);
            }
          }
          
          connectionStateRef.current = 'idle';
          reportError(`WebSocket error event`);
        };

        ws.onopen = () => {
          clearTimeout(connectionTimeoutRef);
          console.log('WebSocket connected successfully to:', url);
          connectionStateRef.current = 'connected';
          updateStatus('connected');
          // Reset reconnect attempts on successful connection
          reconnectAttemptRef.current = 0;
          isReconnectingRef.current = false;
          resourceLimitErrorRef.current = false;
          // Start the keepalive pings
          startPingInterval();
        };
        
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data as string);
            
            // Check if this is an artifact-related message 
            const artifactMessageTypes = [
              'artifact_create_init', 
              'artifact_update_init', 
              'artifact_delta', 
              'artifact_finish', 
              'artifact_suggestion'
            ];
            
            if (data.type && artifactMessageTypes.includes(data.type)) {
              // Pass to the artifact message handler
              onMessage?.(data);
              return;
            }
            
            // Otherwise, handle normal chat message
            const chunk = data as OllamaStreamChunk;

            if (chunk.error) {
              reportError(`Error from backend: ${chunk.error}`);
              return;
            }

            const content = chunk.choices?.[0]?.delta?.content;
            const finishReason = chunk.choices?.[0]?.finish_reason;
            const done = chunk.done;

            if (content) {
              setMessages((prevMessages: UIMessage[]) => {
                let updatedMessages: UIMessage[];
                if (!currentAssistantMessageIdRef.current || prevMessages[prevMessages.length - 1]?.role !== 'assistant') {
                  currentAssistantMessageIdRef.current = generateUUID();
                  // Create a message that matches the UIMessage interface format
                  updatedMessages = [
                    ...prevMessages,
                    { 
                      id: currentAssistantMessageIdRef.current, 
                      role: 'assistant', 
                      content: content,
                      parts: [{ type: 'text', text: content }] 
                    },
                  ];
                } else {
                  updatedMessages = prevMessages.map((msg: UIMessage) => {
                    if (msg.id === currentAssistantMessageIdRef.current) {
                      // Update both content and the text in parts
                      const updatedContent = msg.content + content;
                      return {
                        ...msg,
                        content: updatedContent,
                        parts: [{ type: 'text', text: updatedContent }]
                      };
                    }
                    return msg;
                  });
                }
                onMessagesUpdate?.(updatedMessages);
                return updatedMessages;
              });
            }

            if (finishReason === 'stop' || done) {
              currentAssistantMessageIdRef.current = null;
              updateStatus('connected'); 
            }
          } catch (e: any) {
            reportError(`Error parsing WebSocket message: ${e?.message || String(e)}`);
          }
        };

        ws.onclose = (event) => {
          console.log('WebSocket disconnected:', event.reason, event.code);
          clearTimeout(connectionTimeoutRef);
          
          // Decrement connection counter
          if (window.__wsConnectionCount !== undefined) {
            window.__wsConnectionCount = Math.max(0, window.__wsConnectionCount - 1);
            console.log(`Reduced active WebSocket connections: ${window.__wsConnectionCount}`);
          }
          
          // Only attempt reconnect if we're not already disconnecting intentionally
          if (connectionStateRef.current === 'disconnecting') {
            console.log('WebSocket closed intentionally, not attempting reconnect');
            connectionStateRef.current = 'idle';
            return;
          }
          
          connectionStateRef.current = 'idle';
          
          if (event.wasClean) {
            updateStatus('disconnected');
          } else {
            // Specific error handling for common WebSocket close codes
            let errorMessage = `WebSocket connection died (code: ${event.code})`;
            
            // Handle specific WebSocket error codes
            switch (event.code) {
              case 1001:
                errorMessage = 'WebSocket connection was closed (going away)';
                break;
              case 1006:
                errorMessage = 'WebSocket connection closed abnormally, likely a network issue';
                break;
              case 1008:
                errorMessage = 'WebSocket connection closed due to policy violation';
                break;
              case 1011:
                errorMessage = 'WebSocket connection closed due to server error';
                break;
              case 1012:
                errorMessage = 'WebSocket connection closed due to server restart';
                break;
              case 1013:
                errorMessage = 'WebSocket connection closed due to server overload';
                break;
              case 1015:
                errorMessage = 'WebSocket connection failed (TLS handshake error)';
                break;
            }
            
            reportError(errorMessage);
            
            // Attempt to reconnect if not a clean close and we're not already reconnecting
            if (reconnectAttemptRef.current < maxReconnectAttempts && !isReconnectingRef.current) {
              isReconnectingRef.current = true;
              const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 30000); // Exponential backoff with max 30 seconds
              reconnectAttemptRef.current += 1;
              console.log(`Attempting to reconnect in ${delay}ms. Attempt ${reconnectAttemptRef.current} of ${maxReconnectAttempts}`);
              
              // Clear any existing timeout
              if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
              }
              
              // Set new timeout for reconnection
              reconnectTimeoutRef.current = setTimeout(() => {
                console.log(`Reconnecting... Attempt ${reconnectAttemptRef.current}`);
                setupWebSocket();
              }, delay);
            } else if (reconnectAttemptRef.current >= maxReconnectAttempts) {
              console.error(`Maximum reconnection attempts (${maxReconnectAttempts}) reached.`);
              updateStatus('error');
            }
          }
          currentAssistantMessageIdRef.current = null;
        };
      } catch (error) {
        console.error('Error creating WebSocket:', error);
        reportError(`Failed to create WebSocket: ${error}`);
      }
    };

    try {
      if (wsBaseUrl.startsWith('ws:') || wsBaseUrl.startsWith('wss:')) {
        // Absolute WebSocket URL already provided
        wsUrl = `${wsBaseUrl}${wsBaseUrl.includes('?') ? '&' : '?'}token=${encodeURIComponent(accessToken)}`;
      } else {
        // Relative URL, construct it based on the current protocol and host
        const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        
        // Extract hostname and port
        const hostname = window.location.hostname;
        // For any host (IP address or localhost), use port 8000 where backend is likely running
        const port = '8000';
        const host = `${hostname}:${port}`;
        
        const path = wsBaseUrl.startsWith('/') ? wsBaseUrl : `/${wsBaseUrl}`;
        wsUrl = `${scheme}//${host}${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(accessToken)}`;
      }
      console.log('Constructing WebSocket URL:', wsUrl);
      tryConnect(wsUrl);
    } catch (error) {
      console.error('Error constructing WebSocket URL:', error);
      reportError(`Failed to construct WebSocket URL: ${error}`);
    }
  }, [chatId, accessToken, isAuthenticated, authIsLoading, updateStatus, reportError, onMessagesUpdate, onMessage, startPingInterval]);

  // Setup WebSocket on initial render and when dependencies change
  useEffect(() => {
    console.log('Setup WebSocket effect triggered, current state:', connectionStateRef.current);
    
    // Reset any existing connections when dependencies change
    resetConnectionState();
    
    // Only set up new connection if dependencies are ready
    if (chatId && isAuthenticated && !authIsLoading && accessToken) {
      // Add a small delay to ensure any previous connections are properly closed
      setTimeout(() => {
        setupWebSocket();
      }, 100);
    } else {
      console.log('Cannot set up WebSocket - missing required dependencies');
      updateStatus(isAuthenticated && chatId ? 'idle' : 'disconnected');
    }
    
    return () => {
      // Clean up connection and timeouts when component unmounts or dependencies change
      console.log('Cleanup WebSocket hook, current state:', connectionStateRef.current);
      resetConnectionState();
    };
  }, [chatId, accessToken, isAuthenticated, authIsLoading, setupWebSocket, resetConnectionState, updateStatus]);

  const sendMessage = useCallback((messageText: string, messageModelId?: string) => {
    if (!webSocketRef.current || webSocketRef.current.readyState !== WebSocket.OPEN) {
      reportError('WebSocket is not connected. Cannot send message.');
      // TODO: Queue message and send on reconnect? Or notify user.
      return;
    }

    if (!chatId) {
      reportError('Chat ID is not set. Cannot send message.');
      return;
    }

    const payload: WebSocketSendMessage = {
      room_id: chatId,
      msg: messageText,
    };

    const modelToSend = messageModelId || modelId;
    if (modelToSend) {
      payload.model = modelToSend;
    }

    webSocketRef.current.send(JSON.stringify(payload));
    // User message should be added to state optimistically by the calling component (chat.tsx)
    // updateStatus('awaiting_response'); // Or similar to indicate waiting for stream
  }, [chatId, reportError, modelId]);

  // Return messages state from this hook as well if chat.tsx will solely rely on this hook for messages
  return { messages, setMessages, wsStatus, sendMessage }; 
} 