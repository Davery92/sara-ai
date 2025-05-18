'use server';

import { z } from 'zod';

import { createUser, getUser } from '@/lib/db/queries';

export const authFormSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

export interface LoginActionState {
  status: 'idle' | 'in_progress' | 'success' | 'failed' | 'invalid_data';
}

export const login = async (
  _: LoginActionState,
  formData: FormData,
): Promise<LoginActionState> => {
  try {
    const validatedData = authFormSchema.parse({
      email: formData.get('email'),
      password: formData.get('password'),
    });

    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: validatedData.email, password: validatedData.password }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Login failed' }));
      console.error('Login action failed:', response.status, errorData);
      return { status: 'failed' };
    }
    return { status: 'success' };
  } catch (error) {
    if (error instanceof z.ZodError) {
      return { status: 'invalid_data' };
    }

    return { status: 'failed' };
  }
};

export interface RegisterActionState {
  status:
    | 'idle'
    | 'in_progress'
    | 'success'
    | 'failed'
    | 'user_exists'
    | 'invalid_data';
}

export const register = async (
  _: RegisterActionState,
  formData: FormData,
): Promise<RegisterActionState> => {
  try {
    const validatedData = authFormSchema.parse({
      email: formData.get('email'),
      password: formData.get('password'),
    });

    const [user] = await getUser(validatedData.email);

    if (user) {
      return { status: 'user_exists' } as RegisterActionState;
    }
    await createUser(validatedData.email, validatedData.password);
    const signupResponse = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: validatedData.email, password: validatedData.password }),
    });
    if (!signupResponse.ok) {
      const errorData = await signupResponse.json().catch(() => ({ detail: 'Registration failed' }));
      if (signupResponse.status === 409) {
        return { status: 'user_exists' };
      }
      console.error('Signup action failed:', signupResponse.status, errorData);
      return { status: 'failed' };
    }
    const loginResponse = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: validatedData.email, password: validatedData.password }),
    });
    if (!loginResponse.ok) {
      console.error('Post-signup login failed');
      return { status: 'failed' };
    }
    return { status: 'success' };
  } catch (error) {
    if (error instanceof z.ZodError) {
      return { status: 'invalid_data' };
    }

    return { status: 'failed' };
  }
};
