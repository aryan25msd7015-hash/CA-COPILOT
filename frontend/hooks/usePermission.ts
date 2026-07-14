'use client';
import { useAuth } from './useAuth';
import { Role } from '@/types';

const PERMS: Record<string, Role[]> = {
  'export:reconciliation':  ['partner', 'manager'],
  'approve:notice_draft':   ['partner'],
  'approve:working_paper':  ['partner', 'manager'],
  'send:whatsapp_manual':   ['partner', 'manager'],
  'view:benchmarking':      ['partner'],
  'upload:document':        ['partner', 'manager', 'article'],
  'manage:users':           ['partner'],
  'clear:fraud_flag':       ['partner'],
  'delete:client':          ['partner'],
};

export function usePermission(action: string): boolean {
  const { user } = useAuth();
  if (!user) return false;
  return PERMS[action]?.includes(user.role) ?? false;
}
