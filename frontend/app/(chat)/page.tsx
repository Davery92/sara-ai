import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { Chat } from '@/components/chat';
import { DEFAULT_CHAT_MODEL } from '@/lib/ai/models';
import { generateUUID } from '@/lib/utils';
import { ErrorUI } from '@/components/error-ui';
import { getApiBaseUrl } from '@/lib/get-api-base-url';
// import { headers } from 'next/headers'; // Not used currently

export default async function Page() {
  console.log("RENDERING / (chat index) page");

  const id = generateUUID();
  const cookieStore = await cookies(); // Ensure cookies() is awaited
  const accessToken = cookieStore.get('accessToken')?.value;
  
  if (!accessToken) {
    redirect('/login'); // Removed await as redirect doesn't return a Promise
  }
  
  const serverApiBaseUrl = getApiBaseUrl('server');
  console.log(`[CHAT INDEX PAGE] Attempting to create chat. API Base URL: ${serverApiBaseUrl}`);
  // const modelIdFromCookie = cookieStore.get('chat-model'); // Not used in create
  // const modelId = modelIdFromCookie?.value || DEFAULT_CHAT_MODEL; // Not used in create
  
  // Create the chat in the backend first
  try {
    const createChatUrl = `${serverApiBaseUrl}/api/chats`;
    console.log(`[CHAT INDEX PAGE] Calling POST ${createChatUrl}`);
    const response = await fetch(createChatUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        id: id,
        title: 'New Chat', // Default title for new chat
        visibility: 'private' // Default visibility
      }),
      cache: 'no-store' // Ensure fresh data
    });
    
    if (!response.ok) {
      const errorBody = await response.text();
      console.error('Failed to create chat:', response.status, errorBody);
      return (
        <ErrorUI 
          title="Failed to Create Chat"
          message={`We couldn't create a new chat (Status: ${response.status}). Please try again or contact support if the problem persists. Details: ${errorBody}`}
          actionText="Try Again" // Ideally this would re-trigger the creation or redirect to a safe page
          // onActionClick={() => window.location.reload()} // Example: Reload to try again
        />
      );
    }
    
    // Get the created chat to ensure it exists before redirecting
    // const chat = await response.json(); // Not strictly needed if redirecting immediately
    
    // After successful creation, redirect to the chat page
    // Ensure the 'new=true' query parameter is added for new chats
    return redirect(`/chat/${id}?new=true`);
  } catch (error: any) { // Added type annotation for error
    console.error('Error creating chat:', error);
    // Check if it's a redirect error, if so, let it propagate
    if (error && typeof error === 'object' && 'digest' in error && typeof error.digest === 'string' && error.digest.startsWith('NEXT_REDIRECT')) {
      throw error;
    }
    return (
      <ErrorUI 
        title="Connection Error"
        message="Couldn't connect to the chat server. Please check your internet connection and try again."
        actionText="Try Again"
        // onActionClick={() => window.location.reload()} // Example: Reload to try again
      />
    );
  }

  // Fallback content should ideally not be reached if redirect or error UI is always rendered.
  // This was the previous content when logic was commented out.
  // return (
  //   <div>
  //     <h1>Chat Index Page</h1>
  //     <p>This is the main page for chats. Normally, it would create a new chat and redirect.</p>
  //     <a href="/login">Go to Login</a>
  //   </div>
  // );
}
