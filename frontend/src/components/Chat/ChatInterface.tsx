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
  const [personas, setPersonas] = useState<string[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<string>('');
  const [darkMode, setDarkMode] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { user } = useAuth();
  const currentAiMessageRef = useRef<Message | null>(null);

  // Debug: Log message state when it changes
  useEffect(() => {
    console.log('Current messages:', messages);
  }, [messages]);

  // Initialize dark mode from localStorage
  useEffect(() => {
    const savedDarkMode = localStorage.getItem('darkMode') === 'true';
    setDarkMode(savedDarkMode);
    
    // Apply dark mode class to body
    if (savedDarkMode) {
      document.body.classList.add('dark-mode');
    } else {
      document.body.classList.remove('dark-mode');
    }
  }, []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load available personas
  useEffect(() => {
    const loadPersonas = async () => {
      try {
        const personaList = await chatService.getPersonas();
        setPersonas(personaList);
        
        // Default to first persona if available
        if (personaList.length > 0 && !selectedPersona) {
          setSelectedPersona(personaList[0]);
        }
      } catch (error) {
        console.error('Failed to load personas:', error);
      }
    };
    
    if (user) {
      loadPersonas();
    }
  }, [user]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  const toggleDarkMode = () => {
    const newDarkMode = !darkMode;
    setDarkMode(newDarkMode);
    localStorage.setItem('darkMode', newDarkMode.toString());
    
    // Apply/remove the dark-mode class from the body
    if (newDarkMode) {
      document.body.classList.add('dark-mode');
    } else {
      document.body.classList.remove('dark-mode');
    }
  };
  
  const handlePersonaChange = async (event: React.ChangeEvent<HTMLSelectElement>) => {
    const persona = event.target.value;
    setSelectedPersona(persona);
    
    try {
      await chatService.setPersona(persona);
      
      // Add a system message to inform user
      const systemMessage: Message = {
        id: Date.now().toString() + '-system',
        content: `Persona changed to ${persona}`,
        isUser: false,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, systemMessage]);
    } catch (error) {
      console.error('Error setting persona:', error);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!inputValue.trim() || isLoading) return;
    
    // Create a unique ID for the user message with timestamp for extra uniqueness
    const userMsgId = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}-user`;
    
    const userMessage: Message = {
      id: userMsgId,
      content: inputValue.trim(),
      isUser: true,
      timestamp: new Date(),
    };
    
    // First, set ONLY the user message
    console.log('Adding user message:', userMessage);
    setMessages(prevMessages => [...prevMessages, userMessage]);
    
    // Clear input and set loading state
    setInputValue('');
    setIsLoading(true);
    setTokenError(false);
    
    try {
      // Format message for the chat API
      const apiMessages = [
        { role: 'user', content: userMessage.content }
      ];
      
      console.log("Sending chat request with messages:", apiMessages);
      
      // Wait briefly to ensure user message is rendered separately
      await new Promise(resolve => setTimeout(resolve, 100));
      
      // Create a unique ID for the AI message with timestamp for extra uniqueness
      const aiMsgId = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}-ai`;
      
      // Create an empty AI message that will be updated with stream chunks
      const aiMessage: Message = {
        id: aiMsgId,
        content: '',
        isUser: false,  // Explicitly mark as AI message
        timestamp: new Date(),
      };
      
      // Add empty AI message that will be filled by streaming response
      console.log('Adding AI message placeholder:', aiMessage);
      
      // Use a separate setMessages call for the AI message
      setMessages(prevMessages => [...prevMessages, aiMessage]);
      
      // Use a separate reference for tracking the AI message ID
      const aiMessageId = aiMsgId;
      
      // Use streaming API with proper content accumulation
      let accumulatedContent = '';
      
      await chatService.sendChatCompletion(apiMessages, (chunk) => {
        // Process streaming chunk
        if (chunk.choices && chunk.choices[0]) {
          const choice = chunk.choices[0];
          
          // Update current AI message content with new delta
          if (choice.delta && choice.delta.content) {
            // Append new content to accumulated content
            accumulatedContent += choice.delta.content;
            
            // Debug log to track which message we're updating
            console.log('Updating message ID:', aiMessageId, 'with new content');
            
            // Update ONLY the AI message with the accumulated content
            setMessages(prevMessages => {
              // Map through messages and only update the one matching our AI ID
              return prevMessages.map(msg => {
                if (msg.id === aiMessageId) {
                  return {
                    ...msg,
                    content: accumulatedContent
                  };
                }
                return msg;
              });
            });
          }
        }
      });
      
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
          id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}-error`,
          content: `Error communicating with the server (${apiError.response?.status || 'unknown status'}):\n\n${errorResponse}`,
          isUser: false,
          timestamp: new Date(),
        };
        setMessages(prevMessages => [...prevMessages, errorMessage]);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleTokenRefreshed = () => {
    setTokenError(false);
  };

  return (
    <div className={`chat-interface ${darkMode ? 'dark-mode' : ''}`}>
      <div className="chat-header">
        <h2>Chat with AI</h2>
        <div className="chat-controls">
          {user && <div className="user-info">Logged in as: {user.username}</div>}
          
          {personas.length > 0 && (
            <div className="persona-selector">
              <label htmlFor="persona-select">Personality: </label>
              <select 
                id="persona-select"
                value={selectedPersona}
                onChange={handlePersonaChange}
                disabled={isLoading}
              >
                {personas.map((persona) => (
                  <option key={persona} value={persona}>
                    {persona.replace('sara_', '')}
                  </option>
                ))}
              </select>
            </div>
          )}
          
          <button 
            className="theme-toggle" 
            onClick={toggleDarkMode}
            aria-label="Toggle dark mode"
          >
            {darkMode ? '☀️' : '🌙'}
          </button>
        </div>
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