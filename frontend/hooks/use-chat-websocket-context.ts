'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { UIMessage } from 'ai';
import { generateUUID } from '@/lib/utils';
import { useWebSocket as useWebSocketContextRoot, WebSocketStatus, WS_MESSAGE_EVENT } from '@/context/websocket-context';

// Interface for the hook options
export interface UseChatWebSocketOptions {
  chatId?: string;
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
    wsInstance,
    wsStatus, 
    connect, 
    sendMessage: sendRawWsMessageViaContext,
    currentChatId: currentChatIdFromContext 
  } = useWebSocketContextRoot();
  
  const currentAssistantMessageIdRef = useRef<string | null>(null);
  const hasConnectedRef = useRef<boolean>(false);
  const messageListenerRef = useRef<((event: Event) => void) | null>(null);

  // Connect to the WebSocket when chatId changes
  useEffect(() => {
    if (!chatId) return;
    
    // Only connect if we haven't already connected or if the chatId has changed
    if (!hasConnectedRef.current || currentChatIdFromContext !== chatId) {
      console.log(`[WS_HOOK] Effect: Connecting to chat room: ${chatId}`);
      connect(chatId);
      hasConnectedRef.current = true;
    }
    
    // Clean up when component unmounts or chatId changes
    return () => {
      if (hasConnectedRef.current && currentChatIdFromContext === chatId) {
        console.log(`Disconnecting from chat room: ${chatId}`);
        // disconnect();
        hasConnectedRef.current = false;
      }
    };
  }, [chatId, currentChatIdFromContext, connect]);

  // Pass status changes to the callback
  useEffect(() => {
    onStatusChange?.(wsStatus);
  }, [wsStatus, onStatusChange]);

  // Initialize messages when initialMessages changes
  useEffect(() => {
    if (initialMessages && JSON.stringify(initialMessages) !== JSON.stringify(messages)) {
        setMessages(initialMessages);
    }
  }, [initialMessages]);

  // Wrapper for sending messages to format them correctly
  const sendMessage = useCallback((messageText: string, messageModelId?: string): void => {
    if (!messageText.trim()) return;
    console.log(`[WS_HOOK] sendMessage called with: "${messageText}" for chat ${chatId}`);

    if (!wsInstance || wsInstance.readyState !== WebSocket.OPEN) {
        console.warn("[WS_HOOK] WebSocket not connected. Attempting to connect before sending.");
        if (chatId) {
            connect(chatId); 
        }
        onError?.("WebSocket not ready, message not sent. Please wait or try again.");
        return;
    }

    try {
      const payload = {
        room_id: chatId, 
        msg: messageText,
        model: messageModelId || modelId
      };

      const assistantResponseId = generateUUID();
      currentAssistantMessageIdRef.current = assistantResponseId;
      console.log(`[WS_HOOK] Set currentAssistantMessageIdRef for upcoming assistant message: ${assistantResponseId}`);

      sendRawWsMessageViaContext(payload); 
    } catch (error) {
      console.error('[WS_HOOK] Error in sendMessage:', error);
      onError?.(error instanceof Error ? error.message : 'Error sending message');
    }
  }, [chatId, modelId, onError, sendRawWsMessageViaContext, wsInstance, connect]);

  // Set up message handler for WebSocket responses
  useEffect(() => {
    const handleWebSocketMessage = (event: Event) => {
      try {
        const customEvent = event as CustomEvent;
        const data = customEvent.detail;
        
        if (data.type && data.payload) { 
          onMessage?.(data);
          return;
        }

        if (data.error) {
          console.error("[WS_HOOK] Error message from WebSocket:", data.error);
          onError?.(typeof data.error === 'string' ? data.error : JSON.stringify(data.error));
          currentAssistantMessageIdRef.current = null;
          return;
        }
        
        if (data.choices && data.choices.length > 0) {
          const choice = data.choices[0];
          const delta = choice.delta || {};
          const contentChunk = delta.content;

          if (contentChunk) {
            setMessages(prevMessages => {
              const assistantMessageIdForThisStream = currentAssistantMessageIdRef.current;

              if (!assistantMessageIdForThisStream) {
                console.warn("[WS_HOOK] Received content chunk but no currentAssistantMessageIdRef. Creating new message with new ID.");
                const newId = generateUUID();
                const newMessage: UIMessage = {
                  id: newId,
                  role: 'assistant',
                  content: contentChunk,
                  parts: [{ type: 'text', text: contentChunk }],
                  createdAt: new Date(),
                };
                return [...prevMessages, newMessage];
              }

              const lastMessage = prevMessages.length > 0 ? prevMessages[prevMessages.length - 1] : null;
              if (lastMessage && lastMessage.id === assistantMessageIdForThisStream && lastMessage.role === 'assistant') {
                const updatedContent = lastMessage.content + contentChunk;
                const updatedLastMessage: UIMessage = {
                  ...lastMessage,
                  content: updatedContent,
                  parts: [{ type: 'text', text: updatedContent }],
                };
                return [...prevMessages.slice(0, -1), updatedLastMessage];
              } else {
                console.log(`[WS_HOOK] First chunk for new assistant message ${assistantMessageIdForThisStream}. Content: "${contentChunk}"`);
                const newMessage: UIMessage = {
                  id: assistantMessageIdForThisStream,
                  role: 'assistant',
                  content: contentChunk,
                  parts: [{ type: 'text', text: contentChunk }],
                  createdAt: new Date(),
                };
                return [...prevMessages, newMessage];
              }
            });
          }

          if (choice.finish_reason === 'stop' || data.done === true) {
            console.log("[WS_HOOK] Assistant message stream finished.");
            currentAssistantMessageIdRef.current = null; 
          }
        } else if (data.text) { 
            console.warn("[WS_HOOK] Received message without 'choices' array, treating 'text' as content:", data.text);
            setMessages(prevMessages => {
                const assistantMessageId = currentAssistantMessageIdRef.current || generateUUID();
                if (!currentAssistantMessageIdRef.current) {
                    currentAssistantMessageIdRef.current = assistantMessageId;
                }
                const newMessage: UIMessage = {
                    id: assistantMessageId,
                    role: 'assistant',
                    content: data.text,
                    parts: [{type: 'text', text: data.text}],
                    createdAt: new Date(),
                };
                return [...prevMessages, newMessage];
            });
        }
      } catch (error) {
        console.error('[WS_HOOK] Error handling WebSocket message in hook:', error);
      }
    };

    // Store the listener in a ref to ensure the same function is removed
    messageListenerRef.current = handleWebSocketMessage; 
    window.addEventListener(WS_MESSAGE_EVENT, handleWebSocketMessage);
    
    return () => {
      if (messageListenerRef.current) {
        window.removeEventListener(WS_MESSAGE_EVENT, messageListenerRef.current);
        messageListenerRef.current = null; // Clear the ref after removing
      }
    };
  }, [onMessage, setMessages, onError]);

  return {
    messages,
    setMessages,
    wsStatus,
    sendMessage
  };
} 