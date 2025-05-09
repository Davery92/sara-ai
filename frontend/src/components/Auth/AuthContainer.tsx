import React, { useState } from 'react';
import LoginForm from './LoginForm';
import SignupForm from './SignupForm';
import './AuthContainer.css';

const AuthContainer: React.FC = () => {
  const [isLoginView, setIsLoginView] = useState(true);

  const switchToLogin = () => {
    setIsLoginView(true);
  };

  const switchToSignup = () => {
    setIsLoginView(false);
  };

  return (
    <div className="auth-container">
      <div className="auth-content">
        <div className="auth-welcome">
          <h1>Welcome to Sara AI</h1>
          <p>Sign in to get started with your AI chat assistant</p>
        </div>
        {isLoginView ? (
          <LoginForm onSwitchToSignup={switchToSignup} />
        ) : (
          <SignupForm onSwitchToLogin={switchToLogin} />
        )}
      </div>
    </div>
  );
};

export default AuthContainer; 