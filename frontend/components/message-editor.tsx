'use client';

import type { UIMessage } from 'ai';
import { Button } from './ui/button';
import { type Dispatch, type SetStateAction, useEffect, useRef, useState } from 'react';
import { Textarea } from './ui/textarea';
import { deleteTrailingMessages } from '@/app/(chat)/actions';

export type MessageEditorProps = {
  message: UIMessage;
  setMode: Dispatch<SetStateAction<'view' | 'edit'>>;
  setMessages: Dispatch<SetStateAction<UIMessage[]>>;
  reload: () => Promise<string | null | undefined>;
};

export function MessageEditor({
  message,
  setMode,
  setMessages,
  reload,
}: MessageEditorProps) {
  const [draftContent, setDraftContent] = useState(message.content);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = '0px';
      const scrollHeight = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${scrollHeight}px`;
    }
  };

  const onSave = async () => {
    setIsSubmitting(true);

    await deleteTrailingMessages({ id: message.id });

    setMessages((messages) =>
      messages.map((m) =>
        m.id === message.id
          ? {
              ...m,
              content: draftContent,
              parts: [{ type: 'text', text: draftContent }],
            }
          : m,
      ),
    );

    setMode('view');
    setIsSubmitting(false);
  };

  useEffect(() => {
    adjustHeight();
  }, [draftContent]);

  useEffect(() => {
    setDraftContent(message.content);
    adjustHeight();
  }, [message.content]);

  return (
    <div className="flex w-full flex-col gap-2">
      <Textarea
        ref={textareaRef}
        value={draftContent}
        onChange={(e) => {
          setDraftContent(e.target.value);
        }}
        className="max-h-60 resize-none text-base"
        data-testid="message-editor-textarea"
        autoFocus
      />

      <div className="flex items-center justify-end gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setMode('view')}
          data-testid="message-editor-cancel-button"
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={onSave}
          data-testid="message-editor-save-button"
          className="h-fit py-2 px-3"
          disabled={isSubmitting || draftContent === message.content}
        >
          {isSubmitting ? 'Saving...' : 'Save'}
        </Button>
      </div>
    </div>
  );
}
