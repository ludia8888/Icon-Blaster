export interface GeneratedIcon {
  id: string;
  imageUrl: string;
  liked: boolean;
}

export interface GenerateIconsRequest {
  prompt: string;
  count?: number;
}

export interface GenerateIconsResponse {
  icons: GeneratedIcon[];
  successCount: number;
  totalAttempted: number;
  errors?: string[];
}

export interface ApiError {
  error: string;
  details?: string[];
}