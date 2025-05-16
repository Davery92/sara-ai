'use client';

import { ChevronUp } from 'lucide-react';
import Image from 'next/image';
// import type { User } from 'next-auth';
// import { signOut, useSession } from 'next-auth/react';
import { useTheme } from 'next-themes';
import { useAuth } from '@/context/auth-context';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar';
import { useRouter } from 'next/navigation';
import { toast } from './toast';
import { LoaderIcon } from './icons';
// import { guestRegex } from '@/lib/constants';

export function SidebarUserNav() {
  const router = useRouter();
  // const { data, status } = useSession();
  const { setTheme, theme } = useTheme();
  const { user, isLoading: authIsLoading, isAuthenticated, logout } = useAuth();

  // const isGuest = guestRegex.test(data?.user?.email ?? '');
  // const isGuest = true;
  // const status = 'authenticated';
  // const data = { user: { email: 'user@example.com' } };

  const handleAuthAction = () => {
    if (!isAuthenticated) {
      router.push('/login');
    } else {
      logout();
      router.push('/login');
      toast({ type: 'success', description: 'Successfully signed out.' });
    }
  };

  if (authIsLoading) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton className="data-[state=open]:bg-sidebar-accent bg-background data-[state=open]:text-sidebar-accent-foreground h-10 justify-between">
            <div className="flex flex-row gap-2">
              <div className="size-6 bg-zinc-500/30 rounded-full animate-pulse" />
              <span className="bg-zinc-500/30 text-transparent rounded-md animate-pulse">
                Loading auth status
              </span>
            </div>
            <div className="animate-spin text-zinc-500">
              <LoaderIcon />
            </div>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    );
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              data-testid="user-nav-button"
              className="data-[state=open]:bg-sidebar-accent bg-background data-[state=open]:text-sidebar-accent-foreground h-10"
            >
              {isAuthenticated && user ? (
                <>
                  <Image
                    src={`https://avatar.vercel.sh/${user.email}`}
                    alt={user.email ?? 'User Avatar'}
                    width={24}
                    height={24}
                    className="rounded-full"
                  />
                  <span data-testid="user-email" className="truncate">
                    {user.email}
                  </span>
                </>
              ) : (
                <>
                  <div className="size-6 bg-zinc-300 dark:bg-zinc-700 rounded-full" /> 
                  <span className="truncate">Sign In</span>
                </>
              )}
              <ChevronUp className="ml-auto" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            data-testid="user-nav-menu"
            side="top"
            className="w-[--radix-popper-anchor-width]"
          >
            <DropdownMenuItem
              data-testid="user-nav-item-theme"
              className="cursor-pointer"
              onSelect={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
            >
              {`Toggle ${theme === 'light' ? 'dark' : 'light'} mode`}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild data-testid="user-nav-item-auth">
              <button
                type="button"
                className="w-full cursor-pointer"
                onClick={handleAuthAction}
              >
                {isAuthenticated ? 'Sign out' : 'Sign In / Register'}
              </button>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
