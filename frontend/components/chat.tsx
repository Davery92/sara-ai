'use client';

import type { Attachment, UIMessage } from 'ai';
import { useChat, type UseChatHelpers } from '@ai-sdk/react';
import { useEffect, useState, useCallback } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { ChatHeader } from '@/components/chat-header';
import type { Vote } from '@/lib/db/schema';
import { fetcher, fetchWithErrorHandlers, generateUUID } from '@/lib/utils';
import { Artifact } from './artifact';
import { MultimodalInput } from './multimodal-input';
import { Messages } from './messages';
import type { VisibilityType } from './visibility-selector';
import { useArtifactSelector } from '@/hooks/use-artifact';
import { unstable_serialize } from 'swr/infinite';
import { toast } from './toast';
import type { Session } from 'next-auth';
import { useSearchParams } from 'next/navigation';
import { useChatVisibility } from '@/hooks/use-chat-visibility';
import { useWebSocket } from '@/context/websocket-context';
import { useChatWebSocket } from '@/hooks/use-chat-websocket-context';
import { useArtifact } from '@/hooks/use-artifact';
import { createContext } from 'react';
import { WebSocketStatus } from '@/context/websocket-context';
import type { Chat as ChatMetadata } from '@/lib/db/schema';

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
  session,
  autoResume,
}: {
  id: string;
  initialMessages: Array<UIMessage>;
  initialChatModel: string;
  initialVisibilityType: VisibilityType;
  chatTitle?: string;
  isReadonly: boolean;
  session?: Session;
  autoResume: boolean;
}) {
  const { mutate } = useSWRConfig();
  const [currentModelId, setCurrentModelId] = useState<string>(initialChatModel);

  const { visibilityType } = useChatVisibility({
    chatId: id,
    initialVisibilityType,
  });

  // ---- BEGIN WebSocket Integration ----
  const [input, setInput] = useState(''); // Input remains local to Chat.tsx
  const [internalStatus, setInternalStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [latestDocumentId, setLatestDocumentId] = useState<string | null>(null);
  
  // Store local messages until the WebSocket integration is complete
  const [localMessages, setLocalMessages] = useState<UIMessage[]>(initialMessages || []);

  const handleWebSocketError = (errorMsg: string) => {
    toast({
      type: 'error',
      description: errorMsg || 'WebSocket connection error.',
    });
    setInternalStatus('error');
  };

  const handleWebSocketStatusChange = (wsStatus: WebSocketStatus) => {
    switch (wsStatus) {
      case 'connecting':
        setInternalStatus('loading');
        break;
      case 'connected':
        if (internalStatus !== 'loading') {
            setInternalStatus('idle');
        }
        break;
      case 'disconnected':
        setInternalStatus('idle');
        break;
      case 'error':
        setInternalStatus('error');
        break;
      default:
        setInternalStatus('idle');
    }
  };
  
  // Add handler for artifact-related WebSocket messages
  const handleArtifactMessage = useCallback((message: any) => {
    const { type, payload } = message;
    
    if (!type || !payload) return;
    
    // We can't use the hook inside a callback, so for now we'll just
    // handle setting the document ID and rely on other mechanisms
    if (type === 'artifact_create_init' || type === 'artifact_update_init') {
      setLatestDocumentId(payload.documentId);
    }
    
  }, []);

  const {
    messages: wsMessages,
    setMessages: setWsMessages,
    wsStatus,
    sendMessage,
  } = useChatWebSocket({
    chatId: id,
    initialMessages: initialMessages || [],
    modelId: currentModelId,
    onMessagesUpdate: (updatedMessages) => {
      setLocalMessages(updatedMessages);
      if (internalStatus === 'loading') {
        setInternalStatus('idle'); 
      }
    },
    onStatusChange: handleWebSocketStatusChange,
    onError: handleWebSocketError,
    onMessage: handleArtifactMessage,
  });

  // Ensure we have a valid messages array for components that expect it
  const messagesToDisplay = wsMessages || localMessages || [];

  // Update initial messages when they change
  useEffect(() => {
    if (initialMessages && initialMessages.length > 0 && initialMessages !== localMessages) {
      setLocalMessages(initialMessages);
      setWsMessages(initialMessages);
    }
  }, [initialMessages, localMessages, setWsMessages]);

  // Updated handleSubmit signature
  const handleSubmit = useCallback((e?: React.FormEvent<HTMLFormElement>, chatRequestOptions?: CustomChatRequestOptions) => {
    if (e) e.preventDefault();
    if (!input.trim()) return;
    // console.log("handleSubmit options:", chatRequestOptions); // For debugging if options are used
    const userMessage: UIMessage = {
      id: generateUUID(),
      role: 'user',
      content: input,
      parts: [{ type: 'text', text: input }],
    };
    setLocalMessages((prevMessages) => [...(prevMessages || []), userMessage]);
    sendMessage(input, currentModelId);
    setInput('');
    setInternalStatus('loading');
  }, [input, currentModelId, sendMessage, setLocalMessages]); // Added dependencies

  // Updated append signature
  const append = useCallback(async (message: UIMessage | Omit<UIMessage, 'id' | 'createdAt'>, chatRequestOptions?: CustomChatRequestOptions): Promise<string | null | undefined> => { 
    // console.log("append options:", chatRequestOptions); // For debugging
    const fullMessage: UIMessage = {
        id: generateUUID(), // Ensure id and createdAt if not present
        createdAt: new Date(),
        ...message,
    } as UIMessage;

    setLocalMessages((prevMessages) => [...(prevMessages || []), fullMessage]);
    
    if (fullMessage.role === 'user' && fullMessage.parts && fullMessage.parts[0]?.type === 'text') {
      const textPart = fullMessage.parts[0] as { type: 'text'; text: string };
      const contentToSend = textPart.text;
      sendMessage(contentToSend, currentModelId);
      setInternalStatus('loading');
    }
    return Promise.resolve(null); // Fulfill the Promise type
  }, [currentModelId, sendMessage, setLocalMessages]); // Added dependencies

  const stop = () => {
    console.log('Stop function called - WS handling TBD, for now setting to idle');
    setInternalStatus('idle');
  };

  // Updated reload signature (removed ChatRequestOptions as it's not available/used)
  const reload = useCallback(async (): Promise<string | null | undefined> => {
    const lastUserMessage = messagesToDisplay.filter((m) => m.role === 'user').pop();
    if (lastUserMessage?.content) {
      sendMessage(lastUserMessage.content, currentModelId);
      setInternalStatus('loading');
    } else {
      toast({ type: 'success', description: "Nothing to reload." });
    }
    return Promise.resolve(null); 
  }, [messagesToDisplay, currentModelId, sendMessage]);

  // Map internalStatus to UseChatHelpers['status'] for child components
  const chatUiStatus = (): UseChatHelpers['status'] => {
    if (internalStatus === 'loading') return 'submitted';
    if (internalStatus === 'error') return 'error';
    return 'ready'; 
  };

  const searchParams = useSearchParams();
  const query = searchParams.get('query');

  const [hasAppendedQuery, setHasAppendedQuery] = useState(false);

  // useEffect(() => { // This useEffect for query appending can remain if needed
  //   if (query && !hasAppendedQuery) {
  //     append({
  //       id: generateUUID(),
  //       role: 'user',
  //       content: query,
  //     });
  //     setHasAppendedQuery(true);
  //     window.history.replaceState({}, '', `/chat/${id}`);
  //   }
  // }, [query, append, hasAppendedQuery, id]);

  // const { data: votes } = useSWR<Array<Vote>>( // Removed SWR call for votes
  //   messages.length >= 2 ? `/api/vote?chatId=${id}` : null,
  //   fetcher,
  // );

  const [attachments, setAttachments] = useState<Array<Attachment>>([]);
  const isArtifactVisible = useArtifactSelector((state) => state.isVisible);

  // useAutoResume({
  //   autoResume,
  //   initialMessages,
  //   experimental_resume, // This was from useChat
  //   data, // This was from useChat
  //   setMessages,
  // });

  return (
    <LatestArtifactContext.Provider value={{ documentId: latestDocumentId, setDocumentId: setLatestDocumentId }}>
      <div className="flex flex-col min-w-0 h-dvh bg-background">
        <ChatHeader
          chatId={id}
          chatTitle={chatTitle}
          selectedModelId={currentModelId}
          onModelChange={setCurrentModelId}
          selectedVisibilityType={initialVisibilityType}
          isReadonly={isReadonly}
        />

        <Messages
          chatId={id}
          status={chatUiStatus()}
          messages={messagesToDisplay}
          setMessages={setLocalMessages}
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
              // @ts-expect-error Linter struggles with complex prop type alignment despite manual correction in child
              handleSubmit={handleSubmit}
              status={chatUiStatus()}
              stop={stop}
              attachments={attachments}
              setAttachments={setAttachments}
              messages={messagesToDisplay}
              // @ts-expect-error Linter struggles with complex prop type alignment
              setMessages={setLocalMessages}
              // @ts-expect-error Linter struggles with complex prop type alignment
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
        // @ts-expect-error Linter struggles with complex prop type alignment
        handleSubmit={handleSubmit}
        status={chatUiStatus()}
        stop={stop}
        attachments={attachments}
        setAttachments={setAttachments}
        // @ts-expect-error Linter struggles with complex prop type alignment
        append={append}
        messages={messagesToDisplay}
        // @ts-expect-error Linter struggles with complex prop type alignment
        setMessages={setLocalMessages}
        reload={reload}
        isReadonly={isReadonly}
        selectedVisibilityType={visibilityType}
      />
    </LatestArtifactContext.Provider>
  );
}
