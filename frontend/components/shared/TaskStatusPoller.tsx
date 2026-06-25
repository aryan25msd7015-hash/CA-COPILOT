'use client';
import { useEffect, useRef } from 'react';
import { useTaskStatus } from '@/hooks/useTaskStatus';

export default function TaskStatusPoller({ taskId, onSuccess }: {
  taskId: string | null;
  onSuccess?: (result: unknown) => void;
}) {
  const status = useTaskStatus(taskId);
  const completedTask = useRef<string | null>(null);
  useEffect(() => {
    if (taskId && status?.state === 'SUCCESS' && completedTask.current !== taskId) {
      completedTask.current = taskId;
      onSuccess?.(status.result);
    }
  }, [taskId, status, onSuccess]);
  if (!taskId) return null;
  if (!status) return <p className="text-xs text-gray-500">Waiting for task status...</p>;
  if (status.state === 'SUCCESS') return <p className="text-xs font-medium text-green-700">Processing complete</p>;
  if (status.state === 'FAILURE') {
    return <p className="text-xs font-medium text-red-700">{status.error || 'Processing failed'}</p>;
  }
  return <p className="text-xs text-blue-700">Processing: {status.state.toLowerCase()}</p>;
}
