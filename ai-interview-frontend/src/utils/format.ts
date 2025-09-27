// src/utils/format.ts

/**
 * 一个稳健的日期格式化函数
 * @param dateString - 可能为 null, undefined 或无效的日期字符串
 * @returns 格式化后的本地化日期时间字符串，或 'N/A'
 */
export const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) {
    return 'N/A';
  }
  const date = new Date(dateString);
  // 检查日期是否有效
  if (isNaN(date.getTime())) {
    return 'N/A';
  }
  return date.toLocaleString();
};