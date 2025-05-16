'use client';

import { startTransition, useMemo, useState, useEffect } from 'react';
import useSWR from 'swr';

import { saveChatModelAsCookie } from '@/app/(chat)/actions';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { ChatModel } from '@/lib/ai/models';
import { cn } from '@/lib/utils';
import { fetcher } from '@/lib/utils';

import { CheckCircleFillIcon, ChevronDownIcon, SpinnerIcon } from './icons';

interface ModelSelectorProps extends React.ComponentProps<typeof Button> {
  selectedModelId: string;
  onModelChange: (modelId: string) => void;
  className?: string;
}

// Define the API response structure
interface ModelsApiResponse {
  models: ChatModel[];
}

export function ModelSelector({
  selectedModelId,
  onModelChange,
  className,
}: ModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const [optimisticModelId, setOptimisticModelId] = useState(selectedModelId);

  useEffect(() => {
    setOptimisticModelId(selectedModelId);
  }, [selectedModelId]);

  const { data, error, isLoading } = useSWR<ModelsApiResponse>(
    '/v1/models/available',
    fetcher,
    { revalidateOnFocus: false }
  );

  // Extract the models array from the response
  const availableChatModels = data?.models;

  const selectedChatModel = useMemo(
    () =>
      availableChatModels?.find(
        (chatModel: ChatModel) => chatModel.id === optimisticModelId,
      ),
    [optimisticModelId, availableChatModels],
  );

  if (isLoading) {
    return (
      <Button
        variant="outline"
        className={cn("md:px-2 md:h-[34px] w-fit", className)}
        disabled
      >
        <SpinnerIcon className="animate-spin mr-2" />
        Loading Models...
      </Button>
    );
  }

  if (error || !availableChatModels || availableChatModels.length === 0) {
    return (
      <Button
        variant="outline"
        className={cn("md:px-2 md:h-[34px] w-fit", className)}
        disabled
      >
        Models N/A
      </Button>
    );
  }

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger
        asChild
        className={cn(
          'w-fit data-[state=open]:bg-accent data-[state=open]:text-accent-foreground',
          className,
        )}
      >
        <Button
          data-testid="model-selector"
          variant="outline"
          className="md:px-2 md:h-[34px]"
        >
          {selectedChatModel?.name || 'Select Model'}
          <ChevronDownIcon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[300px]">
        {availableChatModels.map((chatModel: ChatModel) => {
          const { id } = chatModel;

          return (
            <DropdownMenuItem
              data-testid={`model-selector-item-${id}`}
              key={id}
              onSelect={() => {
                setOpen(false);
                if (optimisticModelId === id) return;

                setOptimisticModelId(id);
                onModelChange(id);

                startTransition(() => {
                  saveChatModelAsCookie(id);
                });
              }}
              data-active={id === optimisticModelId}
              asChild
            >
              <button
                type="button"
                className="gap-4 group/item flex flex-row justify-between items-center w-full"
              >
                <div className="flex flex-col gap-1 items-start">
                  <div>{chatModel.name}</div>
                  {chatModel.description && (
                    <div className="text-xs text-muted-foreground">
                      {chatModel.description}
                    </div>
                  )}
                </div>

                <div className="text-foreground dark:text-foreground opacity-0 group-data-[active=true]/item:opacity-100">
                  <CheckCircleFillIcon />
                </div>
              </button>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
