'use server';

import { generateText, type UIMessage } from 'ai';
import { cookies } from 'next/headers';
import {
  deleteMessagesByChatIdAfterTimestamp,
  getMessageById,
  updateChatVisiblityById,
} from '@/lib/db/queries';
import type { VisibilityType } from '@/components/visibility-selector';
import { myProvider } from '@/lib/ai/providers';

export async function saveChatModelAsCookie(model: string) {
  const cookieStore = await cookies();
  cookieStore.set('chat-model', model);
}

/* // Commenting out as title generation will move to the backend
export async function generateTitleFromUserMessage({
  message,
}: {
  message: UIMessage;
}) {
  const { text: title } = await generateText({
    model: myProvider.languageModel('title-model'),
    system: `\n\n    - you will generate a short title based on the first message a user begins a conversation with
    - ensure it is not more than 80 characters long
    - the title should be a summary of the user's message
    - do not use quotes or colons`,
    prompt: JSON.stringify(message),
  });

  return title;
}
*/

// Handles deleting trailing messages after an edited message
export async function deleteTrailingMessages({ id }: { id: string }) {
  const [message] = await getMessageById({ id }); // Uses direct DB query

  if (message && message.chatId) {
    await deleteMessagesByChatIdAfterTimestamp({ // Uses direct DB query
      chatId: message.chatId,
      timestamp: message.createdAt,
    });
  }
}

/* // Removed as useChatVisibility hook now handles this directly with the backend API
export async function updateChatVisibility({
  chatId,
  visibility,
}: {
  chatId: string;
  visibility: VisibilityType;
}) {
  await updateChatVisiblityById({ chatId, visibility }); // Uses direct DB query
}
*/
