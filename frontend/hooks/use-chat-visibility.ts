'use client';

import { useCallback, useEffect, useState } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { unstable_serialize } from 'swr/infinite';
import {
  getChatHistoryKey,
} from '@/components/sidebar-history';
import type { Chat } from '@/lib/db/schema';
import type { VisibilityType } from '@/components/visibility-selector';
import { useAuthenticatedFetch } from './use-authenticated-fetch';
import { toast } from '@/components/toast';

export function useChatVisibility({
  chatId,
  initialVisibilityType,
}: {
  chatId: string;
  initialVisibilityType: VisibilityType;
}) {
  console.log(`[useChatVisibility] Hook initialized for chatId: ${chatId}`);
  const { mutate, cache } = useSWRConfig();
  const { authenticatedFetch } = useAuthenticatedFetch();
  
  const historyKey = unstable_serialize(getChatHistoryKey);
  const chatPages: Chat[][] | undefined = cache.get(historyKey)?.data;

  const { data: localVisibility, mutate: setLocalVisibility } = useSWR(
    `${chatId}-visibility`,
    null,
    {
      fallbackData: initialVisibilityType,
    },
  );

  const visibilityType = useCallback(() => {
    if (chatPages) {
      const allChats = chatPages.flat();
      const chatInHistory = allChats.find((chat) => chat.id === chatId);
      if (chatInHistory) return chatInHistory.visibility as VisibilityType;
    }
    return localVisibility || initialVisibilityType;
  }, [chatPages, chatId, localVisibility, initialVisibilityType]);

  const [visibility, setVisibility] = useState<VisibilityType>(visibilityType());

  useEffect(() => {
    setVisibility(visibilityType());
  }, [visibilityType]);

  const updateChatVisibility = useCallback(async (newVisibility: VisibilityType) => {
    if (!chatId) {
      toast({ type: 'error', description: 'Chat ID is missing, cannot update visibility.' });
      return;
    }

    setVisibility(newVisibility);

    try {
      const response = await authenticatedFetch(`/v1/chats/${chatId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visibility: newVisibility }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to update chat visibility');
      }
      toast({ type: 'success', description: `Chat visibility set to ${newVisibility}.` });
    } catch (error) {
      setVisibility(visibility);
      toast({ type: 'error', description: error instanceof Error ? error.message : 'An unknown error occurred' });
    }
  }, [chatId, authenticatedFetch, visibility]);

  return {
    visibilityType: visibility,
    updateChatVisibility,
  };
}
