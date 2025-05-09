# Sara AI Frontend

This is a React-based frontend for the Sara AI project. It provides a ChatGPT-like interface for interacting with the AI backend.

## Features

- User authentication (login/signup)
- Chat interface for sending messages to the AI
- Real-time message display
- Responsive design

## Getting Started

### Prerequisites

- Node.js (v14 or higher)
- npm or yarn
- Sara AI backend running on port 8000

### Installation

1. Install dependencies:
   ```
   npm install
   ```

2. Start the development server:
   ```
   npm start
   ```

3. Open your browser and navigate to `http://localhost:3000`

## API Integration

The frontend communicates with the following backend endpoints:

- `/auth/signup` - Create a new user account
- `/auth/login` - Log in with existing credentials
- `/auth/me` - Get current user information
- `/messages/` - Send a message
- `/v1/chat/completions` - Get AI completions for chat messages

## Project Structure

- `src/components/Auth` - Authentication-related components
- `src/components/Chat` - Chat interface components
- `src/contexts` - React context for state management
- `src/services` - API service for backend communication

## Development

This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).

Available Scripts:

- `npm start` - Runs the app in development mode
- `npm test` - Launches the test runner
- `npm run build` - Builds the app for production
- `npm run eject` - Ejects from Create React App

## Learn More

You can learn more in the [Create React App documentation](https://facebook.github.io/create-react-app/docs/getting-started).

To learn React, check out the [React documentation](https://reactjs.org/).
