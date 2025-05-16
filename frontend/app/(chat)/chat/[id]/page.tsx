import { cookies } from 'next/headers';
import { notFound, redirect } from 'next/navigation';
import type { Metadata, ResolvingMetadata } from 'next'; // Import Metadata types
import { generateUUID } from '@/lib/utils'; // Added import for generateUUID

// import { auth } from '@/app/(auth)/auth'; // Removed NextAuth
import { Chat } from '@/components/chat';
// import { getChatById, getMessagesByChatId } from '@/lib/db/queries'; // Removed direct DB queries
// import { DataStreamHandler } from '@/components/data-stream-handler'; // To be removed if obsolete
import { DEFAULT_CHAT_MODEL } from '@/lib/ai/models';
import type { Chat as ChatMetadata, DBMessage } from '@/lib/db/schema'; // Chat is now ChatMetadata
import type { Attachment, UIMessage, TextPart } from 'ai';
import { ErrorUI } from '@/components/error-ui';
import type { VisibilityType } from '@/components/visibility-selector'; // Ensure this type is available

// Helper function to get API base URL
const getApiBaseUrl = () => {
  // In a server component, typically use environment variables for API routes
  // For local dev, use port 8000 if that's where your API is running
  // return process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  return process.env.INTERNAL_API_BASE_URL || 'http://localhost:8000'; // Fallback for local non-Docker dev
};

// Generate metadata for the page
export async function generateMetadata(
  { params: pageParamsProp }: { params: { id: string } }
): Promise<Metadata> {
  const params = await pageParamsProp;
  console.log(`CHAT/[ID] PAGE: generateMetadata for id: ${params.id}`);
  const cookieStore = await cookies();
  const accessToken = cookieStore.get('accessToken')?.value;
  // const apiBaseUrl = getApiBaseUrl();
  const internalApiBaseUrl = getApiBaseUrl(); // Use new variable name
  let title = 'Chat';

  if (accessToken && params.id) {
    try {
      // const chatMetaResponse = await fetch(`${apiBaseUrl}/api/chats/${params.id}`, {
      const chatMetaResponse = await fetch(`${internalApiBaseUrl}/api/chats/${params.id}`, { // Use internalApiBaseUrl
        headers: { 'Authorization': `Bearer ${accessToken}` },
        cache: 'no-store'
      });
      if (chatMetaResponse.ok) {
        const fetchedChatMetadata: ChatMetadata = await chatMetaResponse.json();
        if (fetchedChatMetadata.title) {
          title = fetchedChatMetadata.title;
          console.log(`CHAT/[ID] PAGE: generateMetadata found title: ${title}`);
        }
      } else {
        console.log(`CHAT/[ID] PAGE: generateMetadata failed to fetch chat title, status: ${chatMetaResponse.status}`);
      }
    } catch (error) {
      console.error('CHAT/[ID] PAGE: generateMetadata error fetching chat title:', error);
    }
  }
  return {
    title: title,
  };
}

export default async function Page({ 
  params: pageParams,
  searchParams: pageSearchParams
}: { 
  params: { id: string },
  searchParams: { [key: string]: string | string[] | undefined }
}) {
  console.log("---------------------------------------------------------");
  const resolvedSearchParams = await pageSearchParams;
  const resolvedParams = await pageParams;

  console.log(`CHAT/[ID] PAGE: STARTING RENDER FOR ID: ${resolvedParams.id}`);
  
  if (resolvedParams.id === 'undefined') {
    console.log("CHAT/[ID] PAGE: chatId is 'undefined', redirecting to / to create a new chat properly.");
    redirect('/'); 
  }
  
  const chatId = resolvedParams.id;
  const isNew = resolvedSearchParams.new === 'true';
  console.log(`CHAT/[ID] PAGE: chatId: ${chatId}, isNew: ${isNew}`);
  
  const cookieStore = await cookies();
  const accessToken = cookieStore.get('accessToken')?.value;
  console.log(`CHAT/[ID] PAGE: Access token present: ${accessToken ? 'Yes' : 'No'}`);

  if (!accessToken) {
    console.log("CHAT/[ID] PAGE: No access token, redirecting to /login");
    redirect('/login'); 
  }

  let chatMetadata: ChatMetadata | null = null;
  let initialMessages: UIMessage[] = [];
  // const apiBaseUrl = getApiBaseUrl();
  const internalApiBaseUrl = getApiBaseUrl(); // Use new variable name
  console.log(`CHAT/[ID] PAGE: API Base URL: ${internalApiBaseUrl}`);

  // Metadata fetching and potential creation logic
  try {
    console.log(`CHAT/[ID] PAGE: Fetching/checking chat metadata for chatId: ${chatId}`);
    // const chatMetaResponse = await fetch(`${apiBaseUrl}/api/chats/${chatId}`, {
    const chatMetaResponse = await fetch(`${internalApiBaseUrl}/api/chats/${chatId}`, { // Use internalApiBaseUrl
      headers: { 'Authorization': `Bearer ${accessToken}` }, cache: 'no-store'
    });
    console.log(`CHAT/[ID] PAGE: Chat metadata response status: ${chatMetaResponse.status}`);

    if (chatMetaResponse.status === 401) {
      console.log("CHAT/[ID] PAGE: Chat metadata fetch returned 401, redirecting to /login");
      redirect('/login');
    }
    
    if (chatMetaResponse.ok) {
      chatMetadata = await chatMetaResponse.json();
      console.log("CHAT/[ID] PAGE: Fetched chat metadata:", chatMetadata);
    } else if (chatMetaResponse.status === 404) {
      if (isNew) {
        console.log(`CHAT/[ID] PAGE: New chat (id: ${chatId}) not found. Will proceed with empty messages. Metadata might be created on first interaction or by component.`);
        // For a new chat, it's okay if metadata isn't found yet. 
        // We can use a default title or let the Chat component handle it.
        // Optionally, create it here if your flow requires it:
        /*
        try {
          const createResponse = await fetch(`${apiBaseUrl}/api/chats`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: chatId, title: 'New Chat', visibility: 'private' }), // Ensure body matches API
            cache: 'no-store'
          });
          if (createResponse.ok) {
            chatMetadata = await createResponse.json();
            console.log("CHAT/[ID] PAGE: Created metadata for new chat on-the-fly:", chatMetadata);
          } else {
            console.error('CHAT/[ID] PAGE: Failed to create metadata for new chat on-the-fly:', await createResponse.text());
          }
        } catch (creationError) {
          console.error('CHAT/[ID] PAGE: Error during on-the-fly chat creation for new chat:', creationError);
        }
        */
      } else { // 404 for an existing chat
        console.log(`CHAT/[ID] PAGE: Chat not found (404) for existing chat id: ${chatId}.`);
        return <ErrorUI title="Chat Not Found" message="The requested chat does not exist." />;
      }
    } else { // Other non-404 errors
       const errorText = await chatMetaResponse.text();
       console.error(`CHAT/[ID] PAGE: Failed to fetch chat metadata: ${errorText}`);
       return <ErrorUI title="Error Loading Chat" message={`Failed to load chat data: ${errorText}`} />;
    }
  } catch (error: any) {
    console.error('CHAT/[ID] PAGE: Outer error fetching/creating chat metadata:', error);
    if (error.digest?.startsWith('NEXT_REDIRECT')) throw error;
    return <ErrorUI title="Connection Error" message="Could not connect to load chat data." />;
  }

  // Fetch messages only if it's an existing chat AND metadata was successfully fetched.
  if (chatMetadata && !isNew) {
    console.log(`CHAT/[ID] PAGE: Existing chat (id: ${chatId}). Fetching messages.`);
    try {
      // const messagesResponse = await fetch(`${apiBaseUrl}/api/chats/${chatId}/messages`, {
      const messagesResponse = await fetch(`${internalApiBaseUrl}/api/chats/${chatId}/messages`, { // Use internalApiBaseUrl
        headers: { 'Authorization': `Bearer ${accessToken}` }, cache: 'no-store'
      });
      if (messagesResponse.ok) {
        const dbMessages: DBMessage[] = await messagesResponse.json();
        initialMessages = dbMessages.map((msg): UIMessage => {
          let combinedTextContent = '';
          let uiMessageParts: TextPart[] = [];

          if (Array.isArray(msg.parts) && msg.parts.length > 0) {
            const textPartsFromDb = msg.parts
              .filter(p => p.type === 'text' && typeof (p as any).text === 'string')
              .map(p => ({ type: 'text', text: (p as any).text as string })) as TextPart[];
            
            if (textPartsFromDb.length > 0) {
              uiMessageParts = textPartsFromDb;
              combinedTextContent = textPartsFromDb.map(p => p.text).join('\n');
            } else {
              console.warn("CHAT/[ID] PAGE: DBMessage parts field did not contain any text parts. Stringifying parts as fallback.", msg.parts);
              combinedTextContent = msg.parts.map(p => JSON.stringify(p)).join('\n'); 
            }
          } else if (typeof (msg as any).content === 'string' && (msg as any).content.trim() !== '') {
            console.warn("CHAT/[ID] PAGE: DBMessage parts field was empty or not an array. Using msg.content as fallback.", msg);
            combinedTextContent = (msg as any).content;
          } else {
            console.warn("CHAT/[ID] PAGE: DBMessage parts field was not an array or was empty, and no fallback content found.", msg.parts);
          }

          if (uiMessageParts.length === 0) {
            uiMessageParts = [{ type: 'text', text: combinedTextContent }];
          }

          let createdAtDate = new Date(msg.createdAt);
          if (isNaN(createdAtDate.getTime())) {
            console.warn(`CHAT/[ID] PAGE: Invalid date format for createdAt: ${msg.createdAt}. Using current date as fallback.`);
            createdAtDate = new Date(); 
          }

          return {
            id: msg.id,
            role: msg.role === 'human' || msg.role === 'user' ? 'user' : 'assistant',
            content: combinedTextContent, 
            parts: uiMessageParts, 
            createdAt: createdAtDate,
          };
        });
        console.log("CHAT/[ID] PAGE: Fetched initial messages (transformed):", initialMessages);
      } else {
        console.error(`CHAT/[ID] PAGE: Failed to fetch messages: ${await messagesResponse.text()}`);
        // Optionally, set an error state or return an ErrorUI component for message fetch failure
      }
    } catch (error) {
      console.error('CHAT/[ID] PAGE: Error fetching messages:', error);
      // Optionally, set an error state or return an ErrorUI component
    }
  } else if (isNew) {
    console.log(`CHAT/[ID] PAGE: New chat (id: ${chatId}), initialMessages will be empty.`);
  } else if (!chatMetadata && !isNew) {
    // This case implies metadata fetch failed for an existing chat, which should have been handled above.
    // However, as a safeguard:
    console.log("CHAT/[ID] PAGE: No chat metadata for existing chat and not new. This shouldn't be reached if errors handled above.");
    return <ErrorUI title="Error" message="Chat data could not be loaded." />;
  }
  
  const currentChatModel = cookieStore.get('chat-model')?.value || DEFAULT_CHAT_MODEL;
  const currentVisibility = (chatMetadata?.visibility as VisibilityType) || 'private';

  console.log("CHAT/[ID] PAGE: Rendering Chat component with chatId:", chatId, "title:", chatMetadata?.title);

  return (
    <Chat
      id={chatId}
      initialMessages={initialMessages}
      initialChatModel={currentChatModel}
      initialVisibilityType={currentVisibility}
      chatTitle={chatMetadata?.title || 'Chat'} 
      isReadonly={false} 
      autoResume={true} 
    />
  );
}
