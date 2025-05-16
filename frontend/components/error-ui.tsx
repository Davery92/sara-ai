'use client';

import { Button } from '@/components/ui/button';
import { useRouter } from 'next/navigation';

interface ErrorUIProps {
  title?: string;
  message: string;
  actionText?: string;
  onAction?: () => void;
}

export function ErrorUI({ 
  title = "Something went wrong", 
  message, 
  actionText = "Try again", 
  onAction 
}: ErrorUIProps) {
  const router = useRouter();
  
  const handleAction = () => {
    if (onAction) {
      onAction();
    } else {
      router.refresh();
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
      <div className="mb-4 text-red-500">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          width="64"
          height="64"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="8" x2="12" y2="12"></line>
          <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
      </div>
      <h2 className="text-2xl font-bold mb-2">{title}</h2>
      <p className="text-muted-foreground mb-6 max-w-md">{message}</p>
      <div className="flex gap-4">
        <Button onClick={() => router.push('/')}>
          Go Home
        </Button>
        <Button variant="outline" onClick={handleAction}>
          {actionText}
        </Button>
      </div>
    </div>
  );
} 