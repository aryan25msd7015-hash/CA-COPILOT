'use client';
import { useState } from 'react';
import axios from 'axios';
import { api } from '@/lib/api';
import TaskStatusPoller from './TaskStatusPoller';

export default function FileUploadZone({ clientId, docType, onUploaded }: {
  clientId: string;
  docType: string;
  onUploaded?: (documentId: string) => void;
}) {
  const [message, setMessage] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);

  async function upload(file: File) {
    if (!clientId) {
      setMessage('Select a client first.');
      return;
    }
    setMessage('Preparing upload...');
    setProgress(0);
    try {
      const presign = await api.post('/documents/upload-url', {
        client_id: clientId,
        doc_type: docType,
        filename: file.name,
        file_size_bytes: file.size,
        mime_type: file.type || undefined,
      });
      setMessage('Uploading to secure storage...');
      await axios.put(presign.data.upload_url, file, {
        headers: { 'Content-Type': presign.data.content_type || file.type || 'application/octet-stream' },
        onUploadProgress: event => setProgress(event.total ? Math.round((event.loaded / event.total) * 100) : 0),
      });
      const process = await api.post(`/documents/${presign.data.document_id}/process`);
      setTaskId(process.data.task_id);
      setMessage('Upload complete.');
      onUploaded?.(presign.data.document_id);
    } catch {
      setMessage('Upload failed. Check storage credentials and try again.');
    }
  }

  return (
    <div
      onDragOver={event => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={event => { event.preventDefault(); setDragging(false); const file = event.dataTransfer.files?.[0]; if (file) upload(file); }}
      className={`rounded-xl border border-dashed p-5 transition ${dragging ? 'border-blue-500 bg-blue-50' : 'bg-gray-50'}`}
    >
      <label className="block cursor-pointer text-center">
        <span className="text-sm font-medium text-gray-700">Drop a file here or choose one to upload</span>
        <span className="mt-1 block text-xs text-gray-500">{docType.replaceAll('_', ' ')}</span>
        <input className="hidden" type="file" onChange={e => e.target.files?.[0] && upload(e.target.files[0])} />
      </label>
      {progress > 0 && progress < 100 && <div className="mt-3 h-2 overflow-hidden rounded bg-gray-200"><div className="h-full bg-blue-600" style={{ width: `${progress}%` }} /></div>}
      {message && <p className="mt-3 text-center text-xs text-gray-600">{message}</p>}
      <div className="mt-2 text-center"><TaskStatusPoller taskId={taskId} /></div>
    </div>
  );
}
