import React from 'react';
import './ChatMessage.css';

interface ChatMessageProps {
  content: string;
  isUser: boolean;
  timestamp?: Date;
}

const ChatMessage: React.FC<ChatMessageProps> = ({ content, isUser, timestamp }) => {
  // Log the message rendering - this will help diagnose issues
  console.log(`Rendering ChatMessage: isUser=${isUser}, content=${content.slice(0, 30)}...`);

  return (
    <div 
      className={`chat-message ${isUser ? 'user-message' : 'ai-message'}`}
      data-user={isUser ? 'true' : 'false'} // Add a data attribute for easy debugging
    >
      <div className="message-avatar">
        {isUser ? '👤' : '🤖'}
      </div>
      <div className="message-content">
        <div className="message-text">{content}</div>
        {timestamp && (
          <div className="message-time">
            {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatMessage; 