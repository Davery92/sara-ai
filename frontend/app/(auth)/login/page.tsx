'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { toast } from '@/components/toast';

import { AuthForm } from '@/components/auth-form';
import { SubmitButton } from '@/components/submit-button';
import { useAuth } from '@/context/auth-context';

// Define a simpler state for managing form submission status
export interface FormState {
  status: 'idle' | 'in_progress' | 'success' | 'failed' | 'invalid_credentials' | 'error';
  message?: string;
}

export default function Page() {
  const router = useRouter();
  const auth = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSuccessful, setIsSuccessful] = useState(false);
  const [formState, setFormState] = useState<FormState>({ status: 'idle' });

  useEffect(() => {
    if (auth.isAuthenticated && !auth.isLoading) {
      router.replace('/'); // or '/chat' if that's your main page
    }
  }, [auth.isAuthenticated, auth.isLoading, router]);

  useEffect(() => {
    if (formState.status === 'success') {
      toast({ type: 'success', description: formState.message || 'Login successful!' });
    } else if (formState.status === 'invalid_credentials') {
      toast({ type: 'error', description: formState.message || 'Invalid credentials!' });
    } else if (formState.status === 'failed') {
      toast({ type: 'error', description: formState.message || 'Login failed!' });
    } else if (formState.status === 'error') {
      toast({ type: 'error', description: formState.message || 'An unexpected error occurred.' });
    }
  }, [formState]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormState({ status: 'in_progress' });

    const formData = new FormData(event.currentTarget);
    const currentEmail = formData.get('email') as string;
    const currentPassword = formData.get('password') as string;
    setEmail(currentEmail);

    if (!currentEmail || !currentPassword) {
      setFormState({ status: 'failed', message: 'Email and password are required.' });
      return;
    }

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: currentEmail, password: currentPassword }),
      });
      // Read JSON once
      const data = await response.json();
      if (response.ok && data.success) {
        // Login successful: update auth context then navigate
        await auth.login();
        router.replace('/');
        return;
      }
      // Handle errors
      if (!response.ok) {
        const msg = data.detail || (response.status === 401 ? 'Invalid credentials' : 'Login failed');
        setFormState({ status: response.status === 401 ? 'invalid_credentials' : 'failed', message: msg });
        return;
      }
      // Fallback for unexpected
      setFormState({ status: 'error', message: 'An unexpected error occurred during login.' });
    } catch (error) {
      console.error('Login error:', error);
      setFormState({ status: 'error', message: 'An unexpected error occurred during login.' });
    }
  };

  return (
    <div className="flex h-dvh w-screen items-start pt-12 md:pt-0 md:items-center justify-center bg-background">
      <div className="w-full max-w-md overflow-hidden rounded-2xl flex flex-col gap-12">
        <div className="flex flex-col items-center justify-center gap-2 px-4 text-center sm:px-16">
          <h3 className="text-xl font-semibold dark:text-zinc-50">Sign In</h3>
          <p className="text-sm text-gray-500 dark:text-zinc-400">
            Use your email and password to sign in
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
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 dark:text-zinc-300">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              className="mt-1 block w-full px-3 py-2 border border-gray-300 dark:border-zinc-700 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm dark:bg-zinc-800 dark:text-zinc-50"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <SubmitButton isSuccessful={isSuccessful} isLoading={formState.status === 'in_progress'}>Sign in</SubmitButton>
          <p className="text-center text-sm text-gray-600 mt-4 dark:text-zinc-400">
            {"Don't have an account? "}
            <Link
              href="/register"
              className="font-semibold text-gray-800 hover:underline dark:text-zinc-200"
            >
              Sign up
            </Link>
            {' for free.'}
          </p>
        </form>
      </div>
    </div>
  );
}
