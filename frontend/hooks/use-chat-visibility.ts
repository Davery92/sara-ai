'use client';

import { useMemo } from 'react';
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

  const visibilityType = useMemo(() => {
    if (chatPages) {
      const allChats = chatPages.flat();
      const chatInHistory = allChats.find((chat) => chat.id === chatId);
      if (chatInHistory) return chatInHistory.visibility as VisibilityType;
    }
    return localVisibility || initialVisibilityType;
  }, [chatPages, chatId, localVisibility, initialVisibilityType]);

  const setVisibilityType = async (updatedVisibilityType: VisibilityType) => {
    setLocalVisibility(updatedVisibilityType, false);

    mutate(
      historyKey,
      (currentChatPages: Chat[][] | undefined) => {
        if (!currentChatPages) return currentChatPages;
        return currentChatPages.map(page => 
          page.map(chat => 
            chat.id === chatId ? { ...chat, visibility: updatedVisibilityType } : chat
          )
        );
      },
      false
    );

    try {
      await authenticatedFetch(`/v1/chats/${chatId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visibility: updatedVisibilityType }),
      });
      toast({ type: 'success', description: 'Chat visibility updated.' });
    } catch (error) {
      toast({ type: 'error', description: 'Failed to update chat visibility.' });
      setLocalVisibility(visibilityType, false);
      mutate(historyKey);
    }
  };

  return { visibilityType, setVisibilityType };
}
