// src/utils/format.ts
export const formatDateTime = (dateString: string | null | undefined, placeholder: string = 'N/A'): string => {
  if (!dateString) {
    return placeholder;
  }
  const date = new Date(dateString);
  // isNaN 是最可靠的检查方式
  if (isNaN(date.getTime()) || date.getTime() === 0) {
    return placeholder;
  }
  return date.toLocaleString();
};