let accessToken: string | null = null;

export const getAccessToken = () => accessToken;
export const setAccessToken = (value: string | null) => { accessToken = value || null; };
export const clearAccessToken = () => { accessToken = null; };
