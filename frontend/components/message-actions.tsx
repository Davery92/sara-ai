import type { UIMessage } from 'ai';
import { useSWRConfig } from 'swr';
import { useCopyToClipboard } from 'usehooks-ts';
import { toast } from '@/components/toast';
import {
  CopyIcon,
  PencilEditIcon,
} from '@/components/icons';
import { cn } from '@/lib/utils';
import { Button } from './ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from './ui/tooltip';
import { memo } from 'react';
import equal from 'fast-deep-equal';
import { useAuthenticatedFetch } from '@/hooks/use-authenticated-fetch';

interface MessageActionsProps {
  message: UIMessage;
  chatId: string;
  isEditing: boolean;
  setIsEditing: (isEditing: boolean) => void;
  isLast: boolean;
  reload: () => void;
}

const MessageActionsComponent = ({
  message,
  chatId,
  isEditing,
  setIsEditing,
  isLast,
  reload,
}: MessageActionsProps) => {
  const { mutate } = useSWRConfig();
  const [_, copyToClipboard] = useCopyToClipboard();
  const { authenticatedFetch } = useAuthenticatedFetch();

  const handleCopy = () => {
    if (message.content) {
      copyToClipboard(message.content);
      toast({ type: 'success', description: 'Message copied to clipboard!' });
    }
  };

  if (isEditing) {
    return null; // Or some editing-specific actions if needed
  }

  return (
    <TooltipProvider delayDuration={0}>
      <div className="flex flex-row gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              className="py-1 px-2 h-fit text-muted-foreground"
              variant="outline"
              onClick={handleCopy}
            >
              <CopyIcon />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Copy</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              data-testid="message-edit"
              className="py-1 px-2 h-fit text-muted-foreground !pointer-events-auto"
              variant="outline"
              onClick={() => setIsEditing(true)}
            >
              <PencilEditIcon />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Edit</TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
};

export const MessageActions = memo(
  MessageActionsComponent,
  (prevProps, nextProps) => {
    if (prevProps.chatId !== nextProps.chatId) return false;
    if (prevProps.isEditing !== nextProps.isEditing) return false;
    if (prevProps.isLast !== nextProps.isLast) return false;
    if (!equal(prevProps.message, nextProps.message)) return false;
    return true;
  },
);
