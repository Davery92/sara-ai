'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { UIMessage } from 'ai';
import { generateUUID } from '@/lib/utils';
import { useWebSocket as useWebSocketContextRoot, WebSocketStatus, WS_MESSAGE_EVENT } from '@/context/websocket-context';
import { useAuth } from '@/context/auth-context';

// Interface for the hook options
export interface UseChatWebSocketOptions {
  chatId: string;
  initialMessages?: UIMessage[];
  modelId?: string;
  onStatusChange?: (status: WebSocketStatus) => void;
  onError?: (error: string) => void;
  onMessage?: (message: any) => void; // For specialized messages like artifacts
}

export interface ChatWebSocketReturnType {
  messages: UIMessage[];
  setMessages: React.Dispatch<React.SetStateAction<UIMessage[]>>;
  wsStatus: WebSocketStatus;
  sendMessage: (messageText: string, messageModelId?: string) => void;
}

export function useChatWebSocket({
  chatId,
  initialMessages = [],
  modelId,
  onStatusChange,
  onError,
  onMessage,
}: UseChatWebSocketOptions): ChatWebSocketReturnType {
  const [messages, setMessages] = useState<UIMessage[]>(initialMessages);
  const { 
    wsInstance,
    wsStatus: contextWsStatus,
    connect: connectViaContext, 
    disconnect: disconnectViaContext,
    sendMessage: sendRawWsMessageViaContext,
    currentChatId: currentChatIdFromContext 
  } = useWebSocketContextRoot();
  
  const { isAuthenticated, isLoading: authIsLoading } = useAuth();
  const hookInstanceId = useRef(generateUUID()); // Unique ID for this hook instance for debugging

  // Local status for this hook instance, can derive from contextWsStatus if needed
  const [localWsStatus, setLocalWsStatus] = useState<WebSocketStatus>(contextWsStatus);

  useEffect(() => {
    setLocalWsStatus(contextWsStatus);
    onStatusChange?.(contextWsStatus); // Propagate status change
  }, [contextWsStatus, onStatusChange]);

  // Effect to manage connection based on chatId and auth state
  useEffect(() => {
    console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Connection Management Effect. Auth Loading: ${authIsLoading}, Auth Authenticated: ${isAuthenticated}, Current Context Chat ID: ${currentChatIdFromContext}, Hook Chat ID: ${chatId}, Context WS Status: ${contextWsStatus}`);
    
    if (!chatId) {
      console.log(`[WS_HOOK ${hookInstanceId.current}] No chatId. Not connecting.`);
      return;
    }

    if (authIsLoading) {
      console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Auth is loading. Deferring WS connection decision.`);
      return; // Wait for auth to settle
    }

    if (isAuthenticated) {
      // If context is not for this chat, or is disconnected/idle/error, request connect
      if (currentChatIdFromContext !== chatId || ['disconnected', 'idle', 'error'].includes(contextWsStatus)) {
        console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Authenticated. Requesting WS connection via context for chatId: ${chatId}. (Context was for ${currentChatIdFromContext || 'none'}, status ${contextWsStatus})`);
        connectViaContext(chatId);
      } else {
        console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Authenticated. WS context already managing or connected to ${chatId} (status: ${contextWsStatus}).`);
      }
    } else {
      console.warn(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Not authenticated. WebSocket connection cannot be established.`);
      // Ensure WebSocket is disconnected if auth is lost
      if (currentChatIdFromContext === chatId && wsInstance && (wsInstance.readyState === WebSocket.OPEN || wsInstance.readyState === WebSocket.CONNECTING)) {
         // This should be handled by WebSocketProvider's own effect on auth change, but good to be defensive.
         console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Auth lost, ensuring WS context disconnects if it was for this chat.`);
         // disconnectViaContext(); // Let WebSocketProvider handle this via its own auth effect
      }
    }
  }, [chatId, isAuthenticated, authIsLoading, connectViaContext, currentChatIdFromContext, contextWsStatus, wsInstance]);

  useEffect(() => {
    if (initialMessages && JSON.stringify(initialMessages) !== JSON.stringify(messages)) {
        setMessages(initialMessages);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialMessages]);

  const currentAssistantMessageIdRef = useRef<string | null>(null);

  const sendMessage = useCallback((messageText: string, messageModelId?: string): void => {
    if (!messageText.trim()) return;
    console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] sendMessage called: "${messageText.substring(0,30)}..."`);

    if (!isAuthenticated) {
        console.warn(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] sendMessage: User not authenticated. Aborting.`);
        onError?.("Cannot send message: User not authenticated.");
        return;
    }

    if (currentChatIdFromContext !== chatId || contextWsStatus !== 'connected' || !wsInstance || wsInstance.readyState !== WebSocket.OPEN) {
        console.warn(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] sendMessage: WS not ready or not for this chat. Context ChatID: ${currentChatIdFromContext}, Hook ChatID: ${chatId}. Context Status: ${contextWsStatus}, WS State: ${wsInstance?.readyState}. Attempting connect.`);
        connectViaContext(chatId); // Attempt to connect if not ready
        onError?.("WebSocket not ready. Please try again shortly.");
        return;
    }

    currentAssistantMessageIdRef.current = generateUUID(); // Generate new ID for expected assistant response
    console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Set currentAssistantMessageIdRef: ${currentAssistantMessageIdRef.current} before sending.`);
    
    const payload = { room_id: chatId, msg: messageText, model: messageModelId || modelId };
    sendRawWsMessageViaContext(payload);
  }, [chatId, modelId, onError, sendRawWsMessageViaContext, wsInstance, connectViaContext, currentChatIdFromContext, contextWsStatus, isAuthenticated]);

  useEffect(() => {
    const handleMessageFromGlobalEvent = (event: Event) => {
      if (currentChatIdFromContext !== chatId) return; // Ensure message is for the current chat being managed by context

      const customEvent = event as CustomEvent;
      const data = customEvent.detail;

      try {
        if (data.type && data.type.startsWith('artifact_')) { 
          onMessage?.(data);
          return;
        }

        if (data.error) {
          console.error(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Error message from stream:`, data.error);
          onError?.(typeof data.error === 'string' ? data.error : JSON.stringify(data.error));
          currentAssistantMessageIdRef.current = null; // Clear ref on error
          return;
        }
        
        const choices = data.choices;
        if (choices && Array.isArray(choices) && choices.length > 0) {
          const choice = choices[0];
          const delta = choice.delta || {};
          const contentChunk = delta.content;
          
          if (typeof contentChunk === 'string' && contentChunk.length > 0) {
            setMessages(prevMessages => {
              const assistantMessageIdToUpdate = currentAssistantMessageIdRef.current;

              if (!assistantMessageIdToUpdate) {
                // This should ideally not happen if ref is set before send and cleared on [DONE]
                const newId = data.id || generateUUID(); // Use message ID from stream if available
                console.warn(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] NO REF or message ID mismatch. Creating new assistant message ${newId} for chunk: "${contentChunk.substring(0,20)}..."`);
                currentAssistantMessageIdRef.current = newId;
                const newMessage: UIMessage = {
                  id: newId, role: 'assistant', content: contentChunk,
                  parts: [{ type: 'text', text: contentChunk }], createdAt: new Date(),
                };
                return [...prevMessages, newMessage];
              }

              const assistantMessageIndex = prevMessages.findIndex(
                msg => msg.id === assistantMessageIdToUpdate && msg.role === 'assistant'
              );

              if (assistantMessageIndex !== -1) {
                const updatedMessages = [...prevMessages];
                const existingMsg = updatedMessages[assistantMessageIndex];
                const updatedContent = existingMsg.content + contentChunk;
                updatedMessages[assistantMessageIndex] = {
                  ...existingMsg, content: updatedContent,
                  parts: [{ type: 'text', text: updatedContent }],
                };
                return updatedMessages;
              } else {
                 // Message with ref ID not found, create new one
                 const newMessage: UIMessage = {
                   id: assistantMessageIdToUpdate, role: 'assistant', content: contentChunk,
                   parts: [{ type: 'text', text: contentChunk }], createdAt: new Date(),
                 };
                 return [...prevMessages, newMessage];
              }
            });
          }

          if (choice.finish_reason === 'stop' || data.done === true) {
            console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Assistant stream finished (Ref: ${currentAssistantMessageIdRef.current}). Clearing ref.`);
            currentAssistantMessageIdRef.current = null; 
          }
        }
      } catch (error) {
        console.error(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Error handling WebSocket message:`, error);
        onError?.(error instanceof Error ? error.message : 'Error processing WebSocket message');
      }
    };

    console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Adding global WS_MESSAGE_EVENT listener.`);
    window.addEventListener(WS_MESSAGE_EVENT, handleMessageFromGlobalEvent);

    return () => {
      console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Removing global WS_MESSAGE_EVENT listener.`);
      window.removeEventListener(WS_MESSAGE_EVENT, handleMessageFromGlobalEvent);
    };
  }, [chatId, currentChatIdFromContext, onMessage, onError, setMessages]);

  return {
    messages,
    setMessages,
    wsStatus: localWsStatus,
    sendMessage
  };
} 