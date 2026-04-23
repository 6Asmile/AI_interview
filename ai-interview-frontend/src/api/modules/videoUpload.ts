import request from '@/api/request';

export interface InitUploadResponse {
  task_id: string;
  upload_id: string;
  chunk_size: number;
  total_chunks: number;
}

export interface ChunkUploadData {
  task_id: string;
  chunk_index: number;
  chunk: Blob;
}

export interface ChunkUploadResponse {
  message: string;
  chunk_index: number;
  progress?: number;
}

export interface MergeUploadData {
  task_id: string;
}

export interface MergeUploadResponse {
  message: string;
  task_id: string;
  merge_task_id: string;
  transcode_enabled: boolean;
}

export interface UploadProgress {
  id: string;
  file_identifier: string;
  file_name: string;
  file_size: number;
  total_chunks: number;
  uploaded_chunks: number;
  status: string;
  progress_percent: number;
}

export interface RecordingStatusResponse {
  has_recording: boolean;
  recording_enabled: boolean;
  video_url: string | null;
  status: 'pending' | 'uploading' | 'transcoding' | 'completed' | 'failed' | null;
  progress: number;
  error_message: string | null;
  message?: string;
}

export const initUploadApi = (filename: string, fileSize: number): Promise<InitUploadResponse> => {
  const fileIdentifier = Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
  const chunkSize = 5 * 1024 * 1024;
  const totalChunks = Math.ceil(fileSize / chunkSize);
  
  return request({
    url: '/init/',
    method: 'post',
    data: { 
      file_identifier: fileIdentifier,
      file_name: filename, 
      file_size: fileSize,
      total_chunks: totalChunks,
      chunk_size: chunkSize
    },
  });
};

export const uploadChunkApi = async (data: ChunkUploadData): Promise<ChunkUploadResponse> => {
  const formData = new FormData();
  formData.append('task_id', data.task_id);
  formData.append('chunk_index', data.chunk_index.toString());
  formData.append('chunk', data.chunk);

  return request({
    url: '/chunk/',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};

export const mergeUploadApi = (data: MergeUploadData): Promise<MergeUploadResponse> => {
  return request({
    url: '/merge/',
    method: 'post',
    data,
  });
};

export class VideoUploader {
  private chunkSize = 5 * 1024 * 1024;
  private taskId = '';
  private totalChunks = 0;
  private uploadedChunks: Set<number> = new Set();
  private onProgress?: (progress: number) => void;

  constructor(options?: { onProgress?: (progress: number) => void }) {
    this.onProgress = options?.onProgress;
  }

  async upload(file: Blob, filename: string): Promise<string> {
    console.log('[VideoUpload] 开始上传，文件名:', filename, '文件大小:', file.size);
    
    const initResponse = await initUploadApi(filename, file.size);
    this.taskId = initResponse.task_id || initResponse.upload_id;
    this.chunkSize = initResponse.chunk_size || this.chunkSize;
    this.totalChunks = initResponse.total_chunks || Math.ceil(file.size / this.chunkSize);

    console.log('[VideoUpload] 初始化完成，taskId:', this.taskId, '总分片数:', this.totalChunks);

    const chunks = this.splitFile(file);
    
    for (let i = 0; i < chunks.length; i++) {
      if (this.uploadedChunks.has(i)) continue;
      
      await uploadChunkApi({
        task_id: this.taskId,
        chunk_index: i,
        chunk: chunks[i],
      });
      
      this.uploadedChunks.add(i);
      const progress = Math.round(((i + 1) / this.totalChunks) * 100);
      this.onProgress?.(progress);
    }

    console.log('[VideoUpload] 分片上传完成，开始合并...');
    
    const mergeResponse = await mergeUploadApi({
      task_id: this.taskId,
    });

    console.log('[VideoUpload] 合并完成，返回task_id:', mergeResponse.task_id);
    return mergeResponse.task_id || this.taskId;
  }

  private splitFile(file: Blob): Blob[] {
    const chunks: Blob[] = [];
    let start = 0;
    
    while (start < file.size) {
      const end = Math.min(start + this.chunkSize, file.size);
      chunks.push(file.slice(start, end));
      start = end;
    }
    
    return chunks;
  }

  getTaskId(): string {
    return this.taskId;
  }
}
