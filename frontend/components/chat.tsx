'use client';

import type { UIMessage } from 'ai';
import type { UseChatHelpers } from '@ai-sdk/react';
import { useEffect, useState, useCallback } from 'react';
import { ChatHeader } from '@/components/chat-header';
import { generateUUID } from '@/lib/utils';
import { Artifact } from './artifact';
import { MultimodalInput } from './multimodal-input';
import { Messages } from './messages';
import type { VisibilityType } from './visibility-selector';
import { useArtifactSelector } from '@/hooks/use-artifact';
import { toast } from './toast';
import { useSearchParams } from 'next/navigation';
import { useChatVisibility } from '@/hooks/use-chat-visibility';
import { useChatWebSocket } from '@/hooks/use-chat-websocket-context';
import { createContext } from 'react';
import { WebSocketStatus } from '@/context/websocket-context';
import type { ExtendedAttachment } from '@/lib/types';

// Create a context for sharing the latest document ID across components
export const LatestArtifactContext = createContext<{
  documentId: string | null;
  setDocumentId: (id: string | null) => void;
}>({
  documentId: null,
  setDocumentId: () => {},
});

// Using the same type alias name as in MultimodalInput for consistency
type CustomChatRequestOptions = { [key: string]: any };

export function Chat({
  id,
  initialMessages,
  initialChatModel,
  initialVisibilityType,
  chatTitle,
  isReadonly,
  autoResume,
}: {
  id: string;
  initialMessages: Array<UIMessage>;
  initialChatModel: string;
  initialVisibilityType: VisibilityType;
  chatTitle?: string;
  isReadonly: boolean;
  autoResume: boolean;
}) {
  const [currentModelId, setCurrentModelId] = useState<string>(initialChatModel);
  const [input, setInput] = useState('');
  const [latestDocumentId, setLatestDocumentId] = useState<string | null>(null);

  const { visibilityType } = useChatVisibility({
    chatId: id,
    initialVisibilityType,
  });

  const handleWebSocketError = useCallback((errorMsg: string) => {
    toast({ type: 'error', description: errorMsg || 'WebSocket connection error.'});
  }, []);

  const handleWebSocketStatusChange = useCallback((wsStatus: WebSocketStatus) => {
    console.log("[Chat.tsx] WebSocket Status Changed:", wsStatus);
  }, []);

  const handleArtifactMessage = useCallback((message: any) => {
    const { type, payload } = message;
    if (!type || !payload) return;
    if (type === 'artifact_create_init' || type === 'artifact_update_init') {
      setLatestDocumentId(payload.documentId);
    }
  }, [setLatestDocumentId]);

  const {
    messages: wsMessages,
    setMessages: setWsMessages,
    wsStatus,
    sendMessage,
  } = useChatWebSocket({
    chatId: id,
    initialMessages: initialMessages || [],
    modelId: currentModelId,
    onStatusChange: handleWebSocketStatusChange,
    onError: handleWebSocketError,
    onMessage: handleArtifactMessage,
  });
  
  const messagesToDisplay = wsMessages;

  const [attachments, setAttachments] = useState<Array<ExtendedAttachment>>([]);
  
  const handleSubmit = useCallback((e?: React.FormEvent<HTMLFormElement>, chatRequestOptions?: CustomChatRequestOptions) => {
    if (e) e.preventDefault();
    if (!input.trim() && attachments.length === 0) return;

    const userMessage: UIMessage = {
      id: generateUUID(),
      role: 'user',
      content: input,
      parts: [{ type: 'text', text: input }],
      experimental_attachments: attachments,
      createdAt: new Date(),
    };
    setWsMessages((prevMessages) => [...(prevMessages || []), userMessage]);

    sendMessage(input, currentModelId, attachments);
    setInput('');
    setAttachments([]);
  }, [input, currentModelId, attachments, sendMessage, setWsMessages, setInput, setAttachments]);

  const append = useCallback(async (message: UIMessage | Omit<UIMessage, 'id' | 'createdAt'>, chatRequestOptions?: CustomChatRequestOptions): Promise<string | null | undefined> => { 
    const fullMessage: UIMessage = {
        id: generateUUID(),
        createdAt: new Date(),
        ...message,
    } as UIMessage;

    setWsMessages((prevMessages) => [...(prevMessages || []), fullMessage]);
    
    if (fullMessage.role === 'user' && fullMessage.parts && fullMessage.parts[0]?.type === 'text') {
      const textPart = fullMessage.parts[0] as { type: 'text'; text: string };
      const contentToSend = textPart.text;
      sendMessage(contentToSend, currentModelId);
    }
    return Promise.resolve(null);
  }, [currentModelId, sendMessage, setWsMessages]);

  const reload = useCallback(async (): Promise<string | null | undefined> => {
    const lastUserMessage = messagesToDisplay.filter((m) => m.role === 'user').pop();
    if (lastUserMessage?.content) {
      sendMessage(lastUserMessage.content, currentModelId);
    } else {
      toast({ type: 'success', description: "Nothing to reload." });
    }
    return Promise.resolve(null); 
  }, [messagesToDisplay, currentModelId, sendMessage]);

  const chatUiStatus = (): UseChatHelpers['status'] => {
    if (wsStatus === 'connecting') return 'submitted'; 
    if (wsStatus === 'error') return 'error';
    if (wsStatus === 'disconnected') { 
        return messagesToDisplay && messagesToDisplay.length > 0 ? 'error' : 'ready'; 
    }
    if (wsStatus === 'idle') {
        return 'ready';
    }
    if (wsStatus === 'connected') {
        if (messagesToDisplay && messagesToDisplay.length > 0) {
            const lastMessage = messagesToDisplay[messagesToDisplay.length - 1];
            if (lastMessage.role === 'user') {
                return 'submitted';
            }
            return 'ready';
        }
        return 'ready';
    }
    
    return 'ready'; 
  };

  const searchParams = useSearchParams();
  const query = searchParams.get('query');

  const [hasAppendedQuery, setHasAppendedQuery] = useState(false);

  useEffect(() => {
    if (query && !hasAppendedQuery && append) {
      append({
        role: 'user',
        content: query,
        parts: [{ type: 'text', text: query}],
      });
      setHasAppendedQuery(true);
      window.history.replaceState({}, '', `/chat/${id}`);
    }
  }, [query, append, hasAppendedQuery, id]);

  const isArtifactVisible = useArtifactSelector((state) => state.isVisible);
  const stop = () => {
    console.log('Stop function called - WS handling TBD, for now setting UI to idle');
  };

  return (
    <LatestArtifactContext.Provider value={{ documentId: latestDocumentId, setDocumentId: setLatestDocumentId }}>
      <div className="flex flex-col min-w-0 h-dvh bg-background">
        <ChatHeader
          chatId={id}
          chatTitle={chatTitle}
          selectedModelId={currentModelId}
          onModelChange={setCurrentModelId}
          selectedVisibilityType={visibilityType}
          isReadonly={isReadonly}
        />

        <Messages
          chatId={id}
          status={chatUiStatus()}
          messages={messagesToDisplay}
          setMessages={setWsMessages}
          reload={reload}
          isReadonly={isReadonly}
          isArtifactVisible={isArtifactVisible}
        />

        <form className="flex mx-auto px-4 bg-background pb-4 md:pb-6 gap-2 w-full md:max-w-3xl">
          {!isReadonly && (
            <MultimodalInput
              chatId={id}
              input={input}
              setInput={setInput}
              handleSubmit={handleSubmit}
              status={chatUiStatus()}
              stop={stop}
              attachments={attachments}
              setAttachments={setAttachments}
              messages={messagesToDisplay}
              setMessages={setWsMessages}
              append={append}
              selectedVisibilityType={visibilityType}
            />
          )}
        </form>
      </div>

      <Artifact
        chatId={id}
        input={input}
        setInput={setInput}
        handleSubmit={handleSubmit}
        status={chatUiStatus()}
        stop={stop}
        attachments={attachments}
        setAttachments={setAttachments}
        append={append}
        messages={messagesToDisplay}
        setMessages={setWsMessages}
        reload={reload}
        isReadonly={isReadonly}
        selectedVisibilityType={visibilityType}
      />
    </LatestArtifactContext.Provider>
  );
}
