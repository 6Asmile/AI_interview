import request from '@/api/request';

export interface GatewayCredential {
  id: number;
  name: string;
  provider: string;
  scope: 'platform' | 'byok';
  legacy_model: number | null;
  secret_hint: string;
  is_active: boolean;
  updated_at: string;
}

export interface ModelDeployment {
  id: number;
  name: string;
  provider: string;
  remote_model: string;
  model_type: string;
  base_url: string;
  credential: number | null;
  priority: number;
  timeout_seconds: number;
  is_active: boolean;
  last_health_status: string;
}

export interface ModelAlias {
  id: number;
  slug: string;
  name: string;
  model_type: string;
  description: string;
  is_active: boolean;
  route_policy?: { targets: Array<{ deployment_detail: ModelDeployment; order: number; is_active: boolean }> };
}

export interface ModelRequestRecord {
  request_id: string;
  task_name: string;
  status: string;
  alias_slug: string;
  deployment_name: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: string;
  latency_ms: number;
  fallback_count: number;
  error_code: string;
  created_at: string;
}

const list = <T>(response: any): T[] => Array.isArray(response) ? response : (response?.results || []);

export const getGatewayCredentialsApi = async (): Promise<GatewayCredential[]> => list(await request({ url: '/gateway/credentials/', method: 'get' }));
export const createGatewayCredentialApi = (data: Record<string, any>): Promise<GatewayCredential> => request({ url: '/gateway/credentials/', method: 'post', data });
export const deleteGatewayCredentialApi = (id: number) => request({ url: `/gateway/credentials/${id}/`, method: 'delete' });
export const getGatewayDeploymentsApi = async (): Promise<ModelDeployment[]> => list(await request({ url: '/gateway/deployments/', method: 'get' }));
export const createGatewayDeploymentApi = (data: Partial<ModelDeployment>): Promise<ModelDeployment> => request({ url: '/gateway/deployments/', method: 'post', data });
export const updateGatewayDeploymentApi = (id: number, data: Partial<ModelDeployment>): Promise<ModelDeployment> => request({ url: `/gateway/deployments/${id}/`, method: 'patch', data });
export const getGatewayAliasesApi = async (): Promise<ModelAlias[]> => list(await request({ url: '/gateway/aliases/', method: 'get' }));
export const getGatewayRequestsApi = async (): Promise<ModelRequestRecord[]> => list(await request({ url: '/gateway/requests/', method: 'get', params: { page_size: 100 } }));
