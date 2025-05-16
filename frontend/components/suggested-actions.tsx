'use client';

import type { UIMessage } from 'ai';
import { Button } from './ui/button';
import { memo } from 'react';
import type { VisibilityType } from './visibility-selector';
import { motion } from 'framer-motion';

// Define a minimal type for options passed to custom handlers, same as in MultimodalInput
type CustomChatRequestOptions = { [key: string]: any };

interface SuggestedActionsProps {
  append: (
    message: UIMessage | Omit<UIMessage, 'id' | 'createdAt'>, 
    options?: CustomChatRequestOptions
  ) => Promise<string | null | undefined>; // Updated type
  chatId: string;
}

function PureSuggestedActions({
  chatId,
  append,
}: SuggestedActionsProps) {
  const suggestedActions = [
    {
      title: 'What are the advantages',
      label: 'of using Next.js?',
      action: 'What are the advantages of using Next.js?',
    },
    {
      title: 'Write code to',
      label: `demonstrate djikstra\'s algorithm`,
      action: `Write code to demonstrate djikstra\'s algorithm`,
    },
    {
      title: 'Help me write an essay',
      label: `about silicon valley`,
      action: `Help me write an essay about silicon valley`,
    },
    {
      title: 'What is the weather',
      label: 'in San Francisco?',
      action: 'What is the weather in San Francisco?',
    },
  ];

  return (
    <div
      data-testid="suggested-actions"
      className="grid sm:grid-cols-2 gap-2 w-full"
    >
      {suggestedActions.map((suggestedAction, index) => (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          transition={{ delay: 0.05 * index }}
          key={`suggested-action-${suggestedAction.title}-${index}`}
          className={index > 1 ? 'hidden sm:block' : 'block'}
        >
          <Button
            variant="ghost"
            onClick={async () => {
              window.history.replaceState({}, '', `/chat/${chatId}`);
              await append({
                role: 'user',
                content: suggestedAction.action,
                parts: [{ type: 'text', text: suggestedAction.action }], 
              });
            }}
            className="text-left border rounded-xl px-4 py-3.5 text-sm flex-1 gap-1 sm:flex-col w-full h-auto justify-start items-start"
          >
            <span className="font-medium">{suggestedAction.title}</span>
            <span className="text-muted-foreground">
              {suggestedAction.label}
            </span>
          </Button>
        </motion.div>
      ))}
    </div>
  );
}

export const SuggestedActions = memo(
  PureSuggestedActions,
  (prevProps: SuggestedActionsProps, nextProps: SuggestedActionsProps) => {
    if (prevProps.chatId !== nextProps.chatId) return false;
    if (prevProps.append !== nextProps.append) return false; 
    return true;
  },
);
