'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import type { UIMessage } from 'ai';
import { generateUUID } from '@/lib/utils';
import { useWebSocket as useWebSocketContextRoot, WebSocketStatus, WS_MESSAGE_EVENT } from '@/context/websocket-context';

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
    wsStatus, 
    connect, 
    disconnect,
    sendMessage: sendRawWsMessageViaContext,
    currentChatId: currentChatIdFromContext 
  } = useWebSocketContextRoot();
  
  const currentAssistantMessageIdRef = useRef<string | null>(null);
  const hookInstanceId = useRef(generateUUID()); // Unique ID for this hook instance for debugging

  useEffect(() => {
    if (!chatId) {
      console.log(`[WS_HOOK ${hookInstanceId.current} for undefined chatId] No chatId provided.`);
      return;
    }
    if (currentChatIdFromContext !== chatId) {
      console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Context is for ${currentChatIdFromContext || 'N/A'}. Requesting connect to ${chatId}.`);
      connect(chatId);
    }
  }, [chatId, currentChatIdFromContext, connect]);

  useEffect(() => {
    onStatusChange?.(wsStatus);
  }, [wsStatus, onStatusChange]);

  useEffect(() => {
    if (initialMessages && JSON.stringify(initialMessages) !== JSON.stringify(messages)) {
        setMessages(initialMessages);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialMessages]);

  const sendMessage = useCallback((messageText: string, messageModelId?: string): void => {
    if (!messageText.trim()) return;
    console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] sendMessage: "${messageText.substring(0,30)}..."`);

    if (currentChatIdFromContext !== chatId || !wsInstance || wsInstance.readyState !== WebSocket.OPEN) {
        console.warn(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] WS not ready or not for this chat. Context ChatID: ${currentChatIdFromContext || 'N/A'}, Hook ChatID: ${chatId}. WS State: ${wsInstance?.readyState}. Attempting connect.`);
        connect(chatId);
        onError?.("WebSocket not ready. Please try again shortly.");
        return;
    }

    try {
      const payload = { room_id: chatId, msg: messageText, model: messageModelId || modelId };
      const assistantResponseId = generateUUID();
      currentAssistantMessageIdRef.current = assistantResponseId;
      console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Set currentAssistantMessageIdRef: ${assistantResponseId}`);
      sendRawWsMessageViaContext(payload); 
    } catch (error) {
      console.error(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Error in sendMessage:`, error);
      onError?.(error instanceof Error ? error.message : 'Error sending message');
    }
  }, [chatId, modelId, onError, sendRawWsMessageViaContext, wsInstance, connect, currentChatIdFromContext]);

  useEffect(() => {
    const handleMessageFromGlobalEvent = (event: Event) => {
      if (currentChatIdFromContext !== chatId) {
        return;
      }

      const customEvent = event as CustomEvent;
      const data = customEvent.detail;

      try {
        if (data.type && data.payload && data.type.startsWith('artifact_')) { 
          onMessage?.(data);
          return;
        }

        if (data.error) {
          console.error(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Error message from stream:`, data.error);
          onError?.(typeof data.error === 'string' ? data.error : JSON.stringify(data.error));
          currentAssistantMessageIdRef.current = null;
          return;
        }
        
        if (data.choices && Array.isArray(data.choices) && data.choices.length > 0) {
          const choice = data.choices[0];
          const delta = choice.delta || {};
          const contentChunk = delta.content;
          
          if (typeof contentChunk === 'string' && contentChunk.length > 0) {
            setMessages(prevMessages => {
              const assistantMessageIdToUpdate = currentAssistantMessageIdRef.current;

              if (!assistantMessageIdToUpdate) {
                const newId = generateUUID(); 
                console.warn(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] NO REF: Creating new assistant message ${newId} for chunk: "${contentChunk.substring(0,20)}..."`);
                currentAssistantMessageIdRef.current = newId; 
                const newMessage: UIMessage = {
                  id: newId, role: 'assistant', content: contentChunk,
                  parts: [{ type: 'text', text: contentChunk }], createdAt: new Date(),
                };
                console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] NO REF: setMessages adding new message:`, newMessage);
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
                console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] APPEND: Appending to ${assistantMessageIdToUpdate}. Chunk: "${contentChunk.substring(0,20)}...". New content length: ${updatedContent.length}.`);
                return updatedMessages;
              } else {
                // This case might happen if the first chunk arrives before the ref is set by sendMessage,
                // or if prevMessages doesn't contain the message with the ID in the ref.
                console.warn(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] REF MISMATCH: Ref ${assistantMessageIdToUpdate} exists, but message not found in state. Creating new message.`);
                 const newMessage: UIMessage = {
                   id: assistantMessageIdToUpdate, role: 'assistant', content: contentChunk,
                   parts: [{ type: 'text', text: contentChunk }], createdAt: new Date(),
                 };
                 console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] REF MISMATCH: setMessages adding new message:`, newMessage);
                 return [...prevMessages, newMessage];
              }
            });
          }

          if (choice.finish_reason === 'stop' || data.done === true) {
            console.log(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Assistant stream finished (Ref: ${currentAssistantMessageIdRef.current}). Clearing ref.`);
            currentAssistantMessageIdRef.current = null; 
          }
        } else {
          if (!(typeof data === 'string' && data.includes("[DONE]")) && !(typeof data === 'object' && Object.keys(data).length === 0) ) {
             console.warn(`[WS_HOOK ${hookInstanceId.current} for ${chatId}] Received WebSocket message in unhandled format:`, data);
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
    wsStatus,
    sendMessage
  };
} 