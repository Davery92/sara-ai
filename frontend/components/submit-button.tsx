'use client';

import { useFormStatus } from 'react-dom';

import { LoaderIcon } from '@/components/icons';

import { Button } from './ui/button';

export function SubmitButton({
  children,
  isSuccessful,
  isLoading,
}: {
  children: React.ReactNode;
  isSuccessful: boolean;
  isLoading?: boolean;
}) {
  const { pending } = useFormStatus();
  const actualLoading = pending || isLoading;

  return (
    <Button
      type={actualLoading ? 'button' : 'submit'}
      aria-disabled={actualLoading || isSuccessful}
      disabled={actualLoading || isSuccessful}
      className="relative"
    >
      {children}

      {(actualLoading || isSuccessful) && (
        <span className="animate-spin absolute right-4">
          <LoaderIcon />
        </span>
      )}

      <output aria-live="polite" className="sr-only">
        {actualLoading || isSuccessful ? 'Loading' : 'Submit form'}
      </output>
    </Button>
  );
}
