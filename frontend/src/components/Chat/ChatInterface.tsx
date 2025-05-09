import React, { useState, useRef, useEffect } from 'react';
import ChatMessage from './ChatMessage';
import { chatService } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import TokenRefresher from '../Auth/TokenRefresher';
import './ChatInterface.css';

interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
}

// Define type for axios error
interface ApiError {
  response?: {
    status: number;
    data?: any;
  };
  message?: string;
}

const ChatInterface: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [tokenError, setTokenError] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { user } = useAuth();

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!inputValue.trim() || isLoading) return;
    
    const userMessage: Message = {
      id: Date.now().toString(),
      content: inputValue.trim(),
      isUser: true,
      timestamp: new Date(),
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setTokenError(false);
    
    try {
      // Format message for the chat API
      const messages = [
        { role: 'user', content: userMessage.content }
      ];
      
      console.log("Sending chat request with messages:", messages);
      
      // Send to chat completions API
      const response = await chatService.sendChatCompletion(messages);
      console.log("Chat completion response:", response);
      
      // Add AI response to chat
      if (response.data && response.data.choices && response.data.choices[0]) {
        const aiMessage: Message = {
          id: Date.now().toString(),
          content: response.data.choices[0].message.content,
          isUser: false,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, aiMessage]);
      } else if (response.data && response.data.error) {
        // Handle error response from backend
        console.error("Chat completion error from API:", response.data.error);
        const errorMessage: Message = {
          id: Date.now().toString(),
          content: `Error from AI service: ${response.data.error}`,
          isUser: false,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, errorMessage]);
      } else {
        console.error("Unexpected response format:", response.data);
        const errorMessage: Message = {
          id: Date.now().toString(),
          content: `Unexpected response format: ${JSON.stringify(response.data, null, 2)}`,
          isUser: false,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, errorMessage]);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      // Check if it's a token error (401)
      const apiError = error as ApiError;
      if (apiError.response && apiError.response.status === 401) {
        setTokenError(true);
      } else {
        // Add detailed error message
        const errorResponse = apiError.response?.data 
          ? JSON.stringify(apiError.response.data, null, 2)
          : apiError.message || 'Unknown error';
        
        const errorMessage: Message = {
          id: Date.now().toString(),
          content: `Error communicating with the server (${apiError.response?.status || 'unknown status'}):\n\n${errorResponse}`,
          isUser: false,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, errorMessage]);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleTokenRefreshed = () => {
    setTokenError(false);
  };

  return (
    <div className="chat-interface">
      <div className="chat-header">
        <h2>Chat with AI</h2>
        {user && <div className="user-info">Logged in as: {user.username}</div>}
      </div>
      
      {tokenError && (
        <TokenRefresher />
      )}
      
      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="empty-chat">
            <p>👋 Start a conversation by sending a message</p>
          </div>
        ) : (
          messages.map(message => (
            <ChatMessage
              key={message.id}
              content={message.content}
              isUser={message.isUser}
              timestamp={message.timestamp}
            />
          ))
        )}
        <div ref={messagesEndRef} />
      </div>
      
      <form className="chat-input-container" onSubmit={handleSendMessage}>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Type a message..."
          disabled={isLoading}
          className="chat-input"
        />
        <button 
          type="submit" 
          disabled={isLoading || !inputValue.trim()}
          className="send-button"
        >
          {isLoading ? '...' : 'Send'}
        </button>
      </form>
    </div>
  );
};

export default ChatInterface; 