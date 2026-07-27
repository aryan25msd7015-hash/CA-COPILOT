'use client';
import { useAuth } from './useAuth';
import { canPerform } from '@/lib/permissions';

export function usePermission(action: string): boolean {
  const { user } = useAuth();
  return canPerform(user?.role, action);
}
