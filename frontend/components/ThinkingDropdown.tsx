'use client';

import React, { useState } from 'react';
import { ChevronDownIcon } from './icons'; // Assuming this icon exists or can be created
import { Markdown } from './markdown'; // To render the content inside
import { cn } from '@/lib/utils';

interface ThinkingDropdownProps {
  content: string;
}

export function ThinkingDropdown({ content }: ThinkingDropdownProps) {
  const [isOpen, setIsOpen] = useState(false); // Default to closed

  return (
    <details
      className="my-2 border border-zinc-200 dark:border-zinc-700 rounded-lg bg-zinc-50 dark:bg-zinc-800/30"
      open={isOpen}
      onToggle={(e: React.SyntheticEvent<HTMLDetailsElement>) =>
        setIsOpen((e.target as HTMLDetailsElement).open)
      }
    >
      <summary className="flex items-center p-2 cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-700/50 rounded-t-lg list-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <ChevronDownIcon
          size={16}
          className={cn(
            'mr-2 transform transition-transform duration-200',
            isOpen ? 'rotate-180' : 'rotate-0',
          )}
        />
        <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Thinking</span>
      </summary>
      <div className="p-3 border-t border-zinc-200 dark:border-zinc-700 rounded-b-lg">
        {/* Use a smaller font size for thinking content if desired */}
        <div className="text-sm">
          <Markdown>{content}</Markdown>
        </div>
      </div>
    </details>
  );
} 