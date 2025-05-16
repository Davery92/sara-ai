import { cookies } from 'next/headers';

import { AppSidebar } from '@/components/app-sidebar';
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar';
import Script from 'next/script';

export default async function Layout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Get cookie with await
  const cookieStore = await cookies();
  const isCollapsed = cookieStore.get('sidebar:state')?.value !== 'true';

  // Create a mock user for development
  const mockUser = {
    name: 'User',
    email: 'user@example.com',
    image: null
  };

  return (
    <>
      <Script
        src="https://cdn.jsdelivr.net/pyodide/v0.23.4/full/pyodide.js"
        strategy="beforeInteractive"
      />
      <SidebarProvider defaultOpen={!isCollapsed}>
        <AppSidebar user={mockUser} />
        <SidebarInset>{children}</SidebarInset>
      </SidebarProvider>
    </>
  );
}
