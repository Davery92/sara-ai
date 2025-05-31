'use client';

import { isToday, isYesterday, subMonths, subWeeks } from 'date-fns';
import { useParams, useRouter } from 'next/navigation';
// import type { User } from 'next-auth'; // Removed NextAuth User
import { useState, useEffect } from 'react'; // Added useEffect
import { toast } from 'sonner';
import { motion } from 'framer-motion';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  useSidebar,
} from '@/components/ui/sidebar';
import type { Chat } from '@/lib/db/schema';
// fetcher might not be needed if authenticatedFetch handles JSON parsing directly
// import { fetcher } from '@/lib/utils'; 
import { ChatItem } from './sidebar-history-item';
import useSWRInfinite, { SWRInfiniteKeyLoader } from 'swr/infinite'; // Import SWRInfiniteKeyLoader
import { LoaderIcon } from './icons';
import { useAuthenticatedFetch } from '@/hooks/use-authenticated-fetch';
import { useAuth } from '@/context/auth-context'; // Import useAuth

type GroupedChats = {
  today: Chat[];
  yesterday: Chat[];
  lastWeek: Chat[];
  lastMonth: Chat[];
  older: Chat[];
};

// Simplified ChatHistory type for SWRInfinite, expecting Chat[] per page
// If backend sends all chats at once, there will be only one "page"
// export interface ChatHistory {
//   chats: Array<Chat>;
//   hasMore: boolean;
// }

// const PAGE_SIZE = 20; // Pagination logic removed for now

const groupChatsByDate = (chats: Chat[]): GroupedChats => {
  const now = new Date();
  const oneWeekAgo = subWeeks(now, 1);
  const oneMonthAgo = subMonths(now, 1);

  return chats.reduce(
    (groups, chat) => {
      const chatDate = new Date(chat.createdAt);

      if (isToday(chatDate)) {
        groups.today.push(chat);
      } else if (isYesterday(chatDate)) {
        groups.yesterday.push(chat);
      } else if (chatDate > oneWeekAgo) {
        groups.lastWeek.push(chat);
      } else if (chatDate > oneMonthAgo) {
        groups.lastMonth.push(chat);
      } else {
        groups.older.push(chat);
      }

      return groups;
    },
    {
      today: [],
      yesterday: [],
      lastWeek: [],
      lastMonth: [],
      older: [],
    } as GroupedChats,
  );
};

// Updated key loader for SWRInfinite
// For now, it fetches all chats, so only one page.
// To reintroduce pagination, this function and backend would need updates.
export const getChatHistoryKey: SWRInfiniteKeyLoader<Chat[]> = (
  pageIndex: number,
  previousPageData: Chat[] | null,
) => {
  if (pageIndex === 0 && (!previousPageData || previousPageData.length === 0)) {
    return '/api/chats'; // Endpoint to fetch all chats for the user
  }
  return null; // No more pages if not index 0 or if previous page had data (implying all fetched)
};

export function SidebarHistory() { // Removed user prop
  const { setOpenMobile } = useSidebar();
  const { id } = useParams(); // Active chat ID
  const { authenticatedFetch } = useAuthenticatedFetch();
  const { isAuthenticated, isLoading: authLoading } = useAuth(); // Get auth state

  const {
    data: chatPages, // This will be Chat[][], an array of pages, each page being Chat[]
    // setSize, // Not used for now as we fetch all in one go
    isValidating,
    isLoading: historyLoading,
    mutate,
    error,
  } = useSWRInfinite<Chat[]>(
    getChatHistoryKey, // Always provide the key function
    async (url: string) => {
      if (!isAuthenticated) {
        throw new Error('Not authenticated');
      }
      const res = await authenticatedFetch(url);
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ message: 'Failed to fetch chat history' }));
        throw new Error(errorData.message || 'Failed to fetch chat history');
      }
      return res.json();
    },
    {
      revalidateIfStale: true,
      revalidateOnFocus: true,
      revalidateOnReconnect: true,
      // Only fetch if authenticated
      isPaused: () => !isAuthenticated,
      // fallbackData: [], // Initial data can be empty or handled by loading/empty states
    }
  );

  const router = useRouter();
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const allChats = chatPages ? chatPages.flat() : [];

  // const hasReachedEnd = chatPages // Logic simplified as we fetch all
  //   ? chatPages.some((page) => page.hasMore === false) 
  //   : false;

  const hasEmptyChatHistory = !historyLoading && !error && allChats.length === 0;

  const handleDelete = async () => {
    if (!deleteId) return;

    const deletePromise = authenticatedFetch(`/v1/chats/${deleteId}`, {
      method: 'DELETE',
    });

    toast.promise(deletePromise, {
      loading: 'Deleting chat...',
      success: () => {
        mutate(
          (currentPages?: Chat[][]) => {
            if (!currentPages) return [];
            // Optimistically update the SWR cache
            const updatedPages = currentPages.map(page => 
              page.filter(chat => chat.id !== deleteId)
            );
            return updatedPages.filter(page => page.length > 0); // Remove empty pages if any
          },
          { revalidate: false } // Don't revalidate immediately after optimistic update
        );
        return 'Chat deleted successfully';
      },
      error: (err: Error) => err.message || 'Failed to delete chat',
    });

    setShowDeleteDialog(false);

    if (deleteId === id) { // If current chat is deleted, navigate to home
      router.push('/');
    }
    setDeleteId(null);
  };

  if (authLoading) { // Show loading state while auth is being checked
    return (
      <SidebarGroup>
        <div className="px-2 py-1 text-xs text-sidebar-foreground/50">
          Loading...
        </div>
        <SidebarGroupContent>
          <div className="flex justify-center items-center h-20">
            <LoaderIcon className="animate-spin" />
          </div>
        </SidebarGroupContent>
      </SidebarGroup>
    );
  }

  if (!isAuthenticated) { // User not logged in
    return (
      <SidebarGroup>
        <SidebarGroupContent>
          <div className="px-2 text-zinc-500 w-full flex flex-row justify-center items-center text-sm gap-2">
            Login to save and revisit previous chats!
          </div>
        </SidebarGroupContent>
      </SidebarGroup>
    );
  }

  if (historyLoading && !chatPages) { // Initial loading state for history
    return (
      <SidebarGroup>
        <div className="px-2 py-1 text-xs text-sidebar-foreground/50">
          Loading Chats...
        </div>
        <SidebarGroupContent>
          <div className="flex flex-col">
            {[44, 32, 28, 64, 52].map((item, index) => (
              <div
                key={index} // Changed key to index for skeleton
                className="rounded-md h-8 flex gap-2 px-2 items-center"
              >
                <div
                  className="h-4 rounded-md flex-1 max-w-[--skeleton-width] bg-sidebar-accent-foreground/10"
                  style={
                    {
                      '--skeleton-width': `${item}%`,
                    } as React.CSSProperties
                  }
                />
              </div>
            ))}
          </div>
        </SidebarGroupContent>
      </SidebarGroup>
    );
  }
  
  if (error) {
    return (
       <SidebarGroup>
        <SidebarGroupContent>
          <div className="px-2 text-red-500 w-full flex flex-row justify-center items-center text-sm gap-2">
            Error loading chat history: {error.message}
          </div>
        </SidebarGroupContent>
      </SidebarGroup>
    );
  }

  if (hasEmptyChatHistory) {
    return (
      <SidebarGroup>
        <SidebarGroupContent>
          <div className="px-2 text-zinc-500 w-full flex flex-row justify-center items-center text-sm gap-2">
            Your conversations will appear here once you start chatting!
          </div>
        </SidebarGroupContent>
      </SidebarGroup>
    );
  }

  const groupedChats = groupChatsByDate(allChats);

  return (
    <>
      <SidebarGroup>
        <SidebarGroupContent>
          <SidebarMenu>
            {allChats.length > 0 && (
                  <div className="flex flex-col gap-6">
                    {groupedChats.today.length > 0 && (
                      <div>
                        <div className="px-2 py-1 text-xs text-sidebar-foreground/50">
                          Today
                        </div>
                        {groupedChats.today.map((chat) => (
                          <ChatItem
                            key={chat.id}
                            chat={chat}
                            isActive={chat.id === id}
                            onDelete={(chatId) => {
                              setDeleteId(chatId);
                              setShowDeleteDialog(true);
                            }}
                            setOpenMobile={setOpenMobile}
                          />
                        ))}
                      </div>
                    )}

                    {groupedChats.yesterday.length > 0 && (
                      <div>
                        <div className="px-2 py-1 text-xs text-sidebar-foreground/50">
                          Yesterday
                        </div>
                        {groupedChats.yesterday.map((chat) => (
                          <ChatItem
                            key={chat.id}
                            chat={chat}
                            isActive={chat.id === id}
                            onDelete={(chatId) => {
                              setDeleteId(chatId);
                              setShowDeleteDialog(true);
                            }}
                            setOpenMobile={setOpenMobile}
                          />
                        ))}
                      </div>
                    )}
                     {groupedChats.lastWeek.length > 0 && (
                      <div>
                        <div className="px-2 py-1 text-xs text-sidebar-foreground/50">
                          Last Week
                        </div>
                        {groupedChats.lastWeek.map((chat) => (
                          <ChatItem
                            key={chat.id}
                            chat={chat}
                            isActive={chat.id === id}
                            onDelete={(chatId) => {
                              setDeleteId(chatId);
                              setShowDeleteDialog(true);
                            }}
                            setOpenMobile={setOpenMobile}
                          />
                        ))}
                      </div>
                    )}
                     {groupedChats.lastMonth.length > 0 && (
                      <div>
                        <div className="px-2 py-1 text-xs text-sidebar-foreground/50">
                          Last Month
                        </div>
                        {groupedChats.lastMonth.map((chat) => (
                          <ChatItem
                            key={chat.id}
                            chat={chat}
                            isActive={chat.id === id}
                            onDelete={(chatId) => {
                              setDeleteId(chatId);
                              setShowDeleteDialog(true);
                            }}
                            setOpenMobile={setOpenMobile}
                          />
                        ))}
                      </div>
                    )}
                     {groupedChats.older.length > 0 && (
                      <div>
                        <div className="px-2 py-1 text-xs text-sidebar-foreground/50">
                          Older
                        </div>
                        {groupedChats.older.map((chat) => (
                          <ChatItem
                            key={chat.id}
                            chat={chat}
                            isActive={chat.id === id}
                            onDelete={(chatId) => {
                              setDeleteId(chatId);
                              setShowDeleteDialog(true);
                            }}
                            setOpenMobile={setOpenMobile}
                          />
                        ))}
                      </div>
                    )}
                  </div>
            )}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>

      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the chat history. This action cannot
              be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setDeleteId(null)}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
