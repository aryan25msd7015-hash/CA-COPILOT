'use client';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

interface TaskStatus {
  state: 'PENDING' | 'STARTED' | 'SUCCESS' | 'FAILURE' | 'RETRY';
  result?: unknown;
  error?: string;
}

export function useTaskStatus(taskId: string | null, intervalMs = 3000) {
  const [status, setStatus] = useState<TaskStatus | null>(null);

  useEffect(() => {
    if (!taskId) return;
    const poll = async () => {
      try {
        const res = await api.get<TaskStatus>(`/tasks/${taskId}/status`);
        setStatus(res.data);
        if (res.data.state === 'SUCCESS' || res.data.state === 'FAILURE') {
          clearInterval(timer);
        }
      } catch {
        // silently retry
      }
    };
    const timer = setInterval(poll, intervalMs);
    poll();
    return () => clearInterval(timer);
  }, [taskId, intervalMs]);

  return status;
}
