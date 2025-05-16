import React, { useEffect, useState } from 'react';

/**
 * Component that handles Server-Sent Events (SSE) connections for data streaming
 * from the backend. This acts as a wrapper around components that need to listen
 * for real-time data updates.
 */
export function DataStreamHandler({ 
  children, 
  url,
  onData,
  onError
}: { 
  children: React.ReactNode;
  url: string;
  onData: (data: any) => void;
  onError?: (error: any) => void;
}) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let eventSource: EventSource | null = null;
    
    try {
      // Create an SSE connection
      eventSource = new EventSource(url);
      
      // Set up event listeners
      eventSource.onopen = () => {
        console.log('SSE connection opened');
        setIsConnected(true);
      };
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          onData(data);
        } catch (err) {
          console.error('Error parsing SSE data:', err);
          if (onError) onError(err);
        }
      };
      
      eventSource.onerror = (err) => {
        console.error('SSE connection error:', err);
        setError(err instanceof Error ? err : new Error('SSE connection error'));
        setIsConnected(false);
        if (onError) onError(err);
        
        // Close and clean up on error
        if (eventSource) {
          eventSource.close();
        }
      };
    } catch (err) {
      console.error('Failed to establish SSE connection:', err);
      setError(err instanceof Error ? err : new Error('Failed to connect'));
      if (onError) onError(err);
    }
    
    // Clean up on unmount
    return () => {
      if (eventSource) {
        console.log('Closing SSE connection');
        eventSource.close();
        setIsConnected(false);
      }
    };
  }, [url, onData, onError]);
  
  // Just render children - this component only handles the connection
  return <>{children}</>;
} 