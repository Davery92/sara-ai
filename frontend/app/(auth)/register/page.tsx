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
    if (formState.status === 'success') {
      toast({ type: 'success', description: 'Account created successfully! You are now logged in.' });
      setIsSuccessful(true);
      router.push('/');
    } else if (formState.status === 'user_exists') {
      toast({ type: 'error', description: formState.message || 'Account already exists!' });
    } else if (formState.status === 'invalid_data') {
      toast({ type: 'error', description: formState.message || 'Invalid data submitted.' });
    } else if (formState.status === 'failed') {
      toast({ type: 'error', description: formState.message || 'Failed to create account!' });
    } else if (formState.status === 'error') {
      toast({ type: 'error', description: formState.message || 'An unexpected error occurred.' });
    }
  }, [formState, router]); // Update dependencies

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormState({ status: 'in_progress' });

    const formData = new FormData(event.currentTarget);
    const currentEmail = formData.get('email') as string;
    const currentPassword = formData.get('password') as string;
    setEmail(currentEmail);

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
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: currentEmail, password: currentPassword }),
      });

      // If we get a redirect, let the browser handle it
      if (response.redirected) {
        window.location.href = response.url;
        return;
      }

      const data = await response.json();

      if (response.ok) {
        if (data.access_token && data.refresh_token) {
          await auth.login(data.access_token, data.refresh_token);
          setFormState({ status: 'success', message: 'Account created successfully! Redirecting...' });
          router.push('/');
        } else {
          setFormState({ status: 'error', message: 'Invalid response from server' });
        }
      } else {
        if (response.status === 409) {
          setFormState({ status: 'user_exists', message: data.detail || 'User already exists' });
        } else if (response.status === 422) {
          setFormState({ status: 'invalid_data', message: data.detail?.[0]?.msg || data.detail || 'Invalid data' });
        } else {
          setFormState({ status: 'failed', message: data.detail || 'Signup failed' });
        }
      }
    } catch (error) {
      console.error('Signup error:', error);
      setFormState({ status: 'error', message: 'An unexpected error occurred.' });
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
