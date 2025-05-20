'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { AuthForm } from '@/components/auth-form';
import { SubmitButton } from '@/components/submit-button';

import { toast } from '@/components/toast';
import { useAuth } from '@/context/auth-context';
// import { useSession } from 'next-auth/react';

// Define a simpler state for managing form submission status (can be reused or a similar one defined)
export interface FormState { // Using the same FormState as login for now, might need adjustment for register specific errors
  status: 'idle' | 'in_progress' | 'success' | 'failed' | 'user_exists' | 'invalid_data' | 'error'; // Added 'user_exists' and 'invalid_data'
  message?: string;
}

export default function Page() {
  const router = useRouter();
  const auth = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState(''); // Add password state
  const [isSuccessful, setIsSuccessful] = useState(false);

  const [formState, setFormState] = useState<FormState>({ status: 'idle' }); // New state for form

  // const { update: updateSession } = useSession();

  useEffect(() => {
    if (auth.isAuthenticated && !auth.isLoading) {
      console.log('[RegisterPage] User is authenticated via AuthContext, redirecting to /');
      const searchParams = new URLSearchParams(window.location.search);
      const redirectUrl = searchParams.get('redirectUrl');
      router.replace(redirectUrl || '/'); // Default to home page
    }
  }, [auth.isAuthenticated, auth.isLoading, router]);

  useEffect(() => {
    if (formState.status === 'success') {
      toast({ type: 'success', description: formState.message || 'Account created successfully! Redirecting...' });
      setIsSuccessful(true);
      // After signup, ensure context is updated
      auth.login();
    } else if (formState.status === 'user_exists') {
      toast({ type: 'error', description: formState.message || 'Account already exists!' });
    } else if (formState.status === 'invalid_data') {
      toast({ type: 'error', description: formState.message || 'Invalid data submitted.' });
    } else if (formState.status === 'failed') {
      toast({ type: 'error', description: formState.message || 'Failed to create account!' });
    } else if (formState.status === 'error') {
      toast({ type: 'error', description: formState.message || 'An unexpected error occurred.' });
    }
  }, [formState, auth]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormState({ status: 'in_progress' });

    const formData = new FormData(event.currentTarget);
    const currentEmail = formData.get('email') as string;
    const currentPassword = formData.get('password') as string;
    // setEmail(currentEmail); // Not strictly needed to set state here if form data is used directly

    if (!currentEmail || !currentPassword) {
      setFormState({ status: 'invalid_data', message: 'Email and password are required.' });
      return;
    }
    if (currentPassword.length < 6) {
      setFormState({ status: 'invalid_data', message: 'Password must be at least 6 characters long.' });
      return;
    }

    try {
      const response = await fetch('/api/auth/signup', {
        method: 'POST',
        credentials: 'include', // Important for any cookies it might set
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: currentEmail, password: currentPassword }),
      });
      
      const data = await response.json(); // API route returns JSON
      
      if (response.ok && data.success) {
        setFormState({ status: 'success', message: 'Account created successfully! Redirecting...' });
        // This is the crucial part: tell AuthContext that login succeeded after signup
        // AuthContext will fetch user data using the new cookies
        await auth.login();
        // Redirection will be handled by the useEffect watching auth.isAuthenticated
      } else {
        // Handle different error cases
        const msg = data.error || (response.status === 409 ? 'User already exists' : 'Signup failed');
        const status = response.status === 409 ? 'user_exists' : response.status === 422 ? 'invalid_data' : 'failed';
        setFormState({ status, message: msg });
      }
    } catch (error) {
      console.error('Signup page handleSubmit error:', error);
      setFormState({ status: 'error', message: 'An unexpected error occurred during signup.' });
    }
  };

  return (
    <div className="flex h-dvh w-screen items-start pt-12 md:pt-0 md:items-center justify-center bg-background">
      <div className="w-full max-w-md overflow-hidden rounded-2xl gap-12 flex flex-col">
        <div className="flex flex-col items-center justify-center gap-2 px-4 text-center sm:px-16">
          <h3 className="text-xl font-semibold dark:text-zinc-50">Sign Up</h3>
          <p className="text-sm text-gray-500 dark:text-zinc-400">
            Create an account with your email and password
          </p>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-4 md:p-8">
        <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Email</label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              className="mt-1 block w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm dark:bg-zinc-800 dark:text-zinc-50"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="password"className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              className="mt-1 block w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm dark:bg-zinc-800 dark:text-zinc-50"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <SubmitButton isSuccessful={isSuccessful} isLoading={formState.status === 'in_progress'}>Sign Up</SubmitButton>
          <p className="text-center text-sm text-gray-600 mt-4 dark:text-zinc-400">
            {'Already have an account? '}
            <Link
              href="/login"
              className="font-semibold text-gray-800 hover:underline dark:text-zinc-200"
            >
              Sign in
            </Link>
            {' instead.'}
          </p>
        </form>
      </div>
    </div>
  );
}
