'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useWebSocket as useWebSocketContext, WebSocketStatus, WS_MESSAGE_EVENT } from '@/context/websocket-context';
import type { UIMessage } from 'ai';
import { generateUUID } from '@/lib/utils';

// Interface for the hook options
export interface UseChatWebSocketOptions {
  chatId: string;
  initialMessages?: UIMessage[];
  modelId?: string;
  onMessagesUpdate?: (messages: UIMessage[]) => void;
  onStatusChange?: (status: WebSocketStatus) => void;
  onError?: (error: string) => void;
  onMessage?: (message: any) => void; // For handling specialized messages like artifacts
}

interface ChatWebSocketReturnType {
  messages: UIMessage[];
  setMessages: React.Dispatch<React.SetStateAction<UIMessage[]>>;
  wsStatus: WebSocketStatus;
  sendMessage: (messageText: string, messageModelId?: string) => void;
}

export function useChatWebSocket({
  chatId,
  initialMessages = [],
  modelId,
  onMessagesUpdate,
  onStatusChange,
  onError,
  onMessage,
}: UseChatWebSocketOptions): ChatWebSocketReturnType {
  const [messages, setMessages] = useState<UIMessage[]>(initialMessages);
  const { 
    wsStatus, 
    connect, 
    disconnect, 
    sendMessage: sendWsMessage, 
    currentChatId 
  } = useWebSocketContext();
  
  const currentAssistantMessageIdRef = useRef<string | null>(null);
  const hasConnectedRef = useRef<boolean>(false);
  const messageListenerRef = useRef<((event: Event) => void) | null>(null);

  // Connect to the WebSocket when chatId changes
  useEffect(() => {
    if (!chatId) return;
    
    // Only connect if we haven't already connected or if the chatId has changed
    if (!hasConnectedRef.current || currentChatId !== chatId) {
      console.log(`Connecting to chat room: ${chatId}`);
      connect(chatId);
      hasConnectedRef.current = true;
    }
    
    // Clean up when component unmounts or chatId changes
    return () => {
      if (hasConnectedRef.current && currentChatId === chatId) {
        console.log(`Disconnecting from chat room: ${chatId}`);
        disconnect();
        hasConnectedRef.current = false;
      }
    };
  }, [chatId, currentChatId, connect, disconnect]);

  // Pass status changes to the callback
  useEffect(() => {
    onStatusChange?.(wsStatus);
  }, [wsStatus, onStatusChange]);

  // Initialize messages when initialMessages changes
  useEffect(() => {
    if (initialMessages && initialMessages.length > 0) {
      setMessages(initialMessages);
    }
  }, [initialMessages]);

  // Wrapper for sending messages to format them correctly
  const sendMessage = useCallback((messageText: string, messageModelId?: string): void => {
    if (!messageText.trim()) return;

    try {
      // If we're not connected to the right chat room, connect first
      if (currentChatId !== chatId) {
        console.log(`Connecting to chat room ${chatId} before sending message`);
        connect(chatId);
        
        // This approach assumes the WebSocketContext will queue messages
        // if they're sent before the connection is established
        hasConnectedRef.current = true;
      }

      const payload = {
        room_id: chatId,
        msg: messageText,
        model: messageModelId || modelId
      };

      // Create a message ID for the assistant's response that we'll expect
      const assistantMessageId = generateUUID();
      currentAssistantMessageIdRef.current = assistantMessageId;

      // Send the message over WebSocket
      sendWsMessage(payload);
    } catch (error) {
      console.error('Error sending message:', error);
      onError?.(error instanceof Error ? error.message : 'Error sending message');
    }
  }, [chatId, modelId, onError, sendWsMessage, connect, currentChatId]);

  // Set up message handler for WebSocket responses
  useEffect(() => {
    // Define the handler function
    const handleWebSocketMessage = (event: Event) => {
      try {
        const customEvent = event as CustomEvent;
        const data = customEvent.detail;
        
        // Check if this is a specialized message type (like artifact)
        if (data.type && data.payload) {
          onMessage?.(data);
          return;
        }

        // Handle standard chat message
        if (data.choices && data.choices.length > 0) {
          const choice = data.choices[0];
          const delta = choice.delta || {};

          // If the message has content, update the messages
          if (delta.content) {
            setMessages(prevMessages => {
              const assistantMessageId = currentAssistantMessageIdRef.current;
              
              // Check if we already have an assistant message being built
              const assistantMessageIndex = prevMessages.findIndex(
                msg => msg.role === 'assistant' && msg.id === assistantMessageId
              );

              if (assistantMessageIndex >= 0) {
                // Update existing message
                const updatedMessages = [...prevMessages];
                updatedMessages[assistantMessageIndex] = {
                  ...updatedMessages[assistantMessageIndex],
                  content: updatedMessages[assistantMessageIndex].content + delta.content
                };
                onMessagesUpdate?.(updatedMessages);
                return updatedMessages;
              } else {
                // Create new assistant message
                const newMessage = {
                  id: assistantMessageId || generateUUID(),
                  role: 'assistant' as const,
                  content: delta.content
                };
                const updatedMessages = [...prevMessages, newMessage as UIMessage];
                onMessagesUpdate?.(updatedMessages);
                return updatedMessages;
              }
            });
          }

          // If this is the end of the message
          if (choice.finish_reason === 'stop') {
            currentAssistantMessageIdRef.current = null;
          }
        }
      } catch (error) {
        console.error('Error handling WebSocket message:', error);
      }
    };

    // Store the handler in a ref so we can remove the same function reference later
    messageListenerRef.current = handleWebSocketMessage;

    // Add the event listener to the global window object
    window.addEventListener(WS_MESSAGE_EVENT, handleWebSocketMessage);

    return () => {
      // Remove the event listener using the same function reference
      if (messageListenerRef.current) {
        window.removeEventListener(WS_MESSAGE_EVENT, messageListenerRef.current);
        messageListenerRef.current = null;
      }
    };
  }, [onMessage, onMessagesUpdate]);

  return {
    messages,
    setMessages,
    wsStatus,
    sendMessage
  };
} 