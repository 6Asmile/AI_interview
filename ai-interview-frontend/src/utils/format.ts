// src/utils/format.ts
import dayjs from 'dayjs';

/**
 * 格式化日期时间字符串
 * @param dateString - 任何可以被 dayjs 解析的日期字符串、Date 对象或 null/undefined
 * @param format - 期望的输出格式，默认为 'YYYY-MM-DD HH:mm:ss'
 * @param placeholder - 当日期无效时显示的占位符
 * @returns 格式化后的日期字符串或占位符
 */
export const formatDateTime = (
  dateString: string | null | undefined | Date, 
  format: string = 'YYYY-MM-DD HH:mm:ss', 
  placeholder: string = 'N/A'
): string => {
  // 检查输入是否为空或无效
  if (!dateString) {
    return placeholder;
  }

  const date = dayjs(dateString);

  // 检查 dayjs 是否成功解析了日期
  if (!date.isValid()) {
    return placeholder;
  }

  return date.format(format);
};