import React, { useState } from 'react';
import { useAuth } from '../../contexts/AuthContext';

const TokenRefresher = () => {
  const [refreshing, setRefreshing] = useState(false);
  const [message, setMessage] = useState('');
  const { checkAndRefreshToken } = useAuth();

  const handleRefresh = async () => {
    setRefreshing(true);
    setMessage('Refreshing tokens...');
    
    try {
      await checkAndRefreshToken();
      setMessage('Tokens refreshed successfully! Try your request again.');
      
      // Force page reload after a short delay to ensure all components use the new token
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } catch (error) {
      console.error('Error refreshing tokens:', error);
      setMessage('Error refreshing tokens: ' + (error.message || 'Unknown error'));
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div style={{ margin: '20px', padding: '20px', border: '1px solid #ccc', borderRadius: '5px', backgroundColor: '#f8d7da' }}>
      <h3>Token Expired</h3>
      <p>Your authentication token has expired. Click the button below to refresh it.</p>
      {message && <p style={{ color: message.includes('successfully') ? 'green' : 'red' }}>{message}</p>}
      <button 
        onClick={handleRefresh} 
        disabled={refreshing}
        style={{
          padding: '8px 16px',
          backgroundColor: refreshing ? '#cccccc' : '#4CAF50',
          color: 'white',
          border: 'none',
          borderRadius: '4px',
          cursor: refreshing ? 'not-allowed' : 'pointer'
        }}
      >
        {refreshing ? 'Refreshing...' : 'Refresh Token'}
      </button>
    </div>
  );
};

export default TokenRefresher; 