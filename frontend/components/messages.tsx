'use client';

import type { UIMessage } from 'ai';
import { memo, type Dispatch, type SetStateAction } from 'react';

import { PreviewMessage, ThinkingMessage } from './message';
import type { UseChatHelpers } from '@ai-sdk/react';
import { motion } from 'framer-motion';
import { useMessages } from '@/hooks/use-messages';
import { Greeting } from './greeting';
import equal from 'fast-deep-equal';
import { Button } from './ui/button';
import { CornerDownLeftIcon } from 'lucide-react';

interface MessagesProps {
  chatId: string;
  status: UseChatHelpers['status'];
  messages: Array<UIMessage>;
  setMessages: Dispatch<SetStateAction<UIMessage[]>>;
  reload: () => Promise<string | null | undefined>;
  isReadonly: boolean;
  isArtifactVisible: boolean;
}

function PureMessages({
  chatId,
  status,
  messages,
  setMessages,
  reload,
  isReadonly,
  isArtifactVisible,
}: MessagesProps) {
  const {
    containerRef: messagesContainerRef,
    endRef: messagesEndRef,
    onViewportEnter,
    onViewportLeave,
    hasSentMessage,
  } = useMessages({
    chatId,
    status,
  });

  return (
    <motion.div
      ref={messagesContainerRef}
      data-testid="messages-container"
      layout="position"
      className="flex flex-col min-w-0 gap-6 flex-1 overflow-y-scroll pt-4 relative"
      onViewportEnter={onViewportEnter}
      onViewportLeave={onViewportLeave}
    >
      {Array.isArray(messages) && messages.length === 0 && <Greeting />}

      {Array.isArray(messages) && messages.map((message, index) => (
        <PreviewMessage
          key={message.id}
          chatId={chatId}
          message={message}
          isLoading={status === 'submitted' && messages.length - 1 === index && message.role !== 'assistant'}
          isReadonly={isReadonly}
          requiresScrollPadding={hasSentMessage && index === messages.length - 1}
          setMessages={setMessages}
          reload={reload}
        />
      ))}

      {status === 'submitted' &&
        messages.length > 0 &&
        messages[messages.length - 1].role === 'user' && <ThinkingMessage />}

      {status !== 'submitted' && messages.length > 0 && !isReadonly && (
        <div className="flex justify-center py-4">
          <Button variant="outline" onClick={() => reload()}>
            <CornerDownLeftIcon className="mr-2 size-4" />
            Regenerate response
          </Button>
        </div>
      )}

      <motion.div
        ref={messagesEndRef}
        className="shrink-0 min-w-[24px] min-h-[24px]"
        layout
      />
    </motion.div>
  );
}

export const Messages = memo(PureMessages, equal);
