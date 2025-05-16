// Test script for authentication flow
// Run this with: node test-auth-flow.js

const fetch = require('node-fetch');

async function testAuthFlow() {
  console.log('Testing Authentication Flow\n');
  
  // Set the base URL for API requests
  let baseUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';
  
  // Ensure baseUrl doesn't end with a slash
  if (baseUrl.endsWith('/')) {
    baseUrl = baseUrl.slice(0, -1);
  }
  
  // 1. Test direct login to backend
  const loginUrl = `${baseUrl}/auth/login`;
  console.log(`1. Testing direct login to backend at: ${loginUrl}`);
  
  try {
    const loginResponse = await fetch(loginUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        username: 'test@example.com', // Change to a valid user
        password: 'password123'       // Change to a valid password
      })
    });
    
    console.log('Login response status:', loginResponse.status);
    
    let loginData;
    try {
      loginData = await loginResponse.json();
    } catch (e) {
      const text = await loginResponse.text();
      console.error('Failed to parse login response as JSON:', text);
      return;
    }
    
    if (loginResponse.ok) {
      console.log('Login successful. Access token received.');
      console.log('Token type:', loginData.token_type);
      console.log('Access token (first 20 chars):', loginData.access_token.substring(0, 20) + '...');
      
      // 2. Test /auth/me with the obtained token
      const meUrl = `${baseUrl}/auth/me`;
      console.log(`\n2. Testing /auth/me with token at: ${meUrl}`);
      
      const meResponse = await fetch(meUrl, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${loginData.access_token}`
        }
      });
      
      console.log('ME response status:', meResponse.status);
      if (meResponse.ok) {
        const userData = await meResponse.json();
        console.log('User data received:', userData);
      } else {
        try {
          const errorData = await meResponse.json();
          console.error('Error response from /auth/me (JSON):', errorData);
        } catch (e) {
          const text = await meResponse.text();
          console.error('Error response from /auth/me (text):', text);
        }
      }
      
      // 3. Test token refresh
      const refreshUrl = `${baseUrl}/auth/refresh`;
      console.log(`\n3. Testing token refresh at: ${refreshUrl}`);
      
      const refreshResponse = await fetch(refreshUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          refresh_token: loginData.refresh_token
        })
      });
      
      console.log('Refresh response status:', refreshResponse.status);
      if (refreshResponse.ok) {
        const refreshData = await refreshResponse.json();
        console.log('Refresh successful. New access token received.');
        console.log('New token type:', refreshData.token_type);
        console.log('New access token (first 20 chars):', refreshData.access_token.substring(0, 20) + '...');
      } else {
        try {
          const errorData = await refreshResponse.json();
          console.error('Error refreshing token (JSON):', errorData);
        } catch (e) {
          const text = await refreshResponse.text();
          console.error('Error refreshing token (text):', text);
        }
      }
    } else {
      console.error('Login failed:', loginData);
    }
  } catch (error) {
    console.error('Error during authentication test:', error);
  }
}

testAuthFlow(); 