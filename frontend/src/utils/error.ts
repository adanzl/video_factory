import { ElMessage } from "element-plus";
import type { AxiosError } from "axios";
import { logger } from "./logger";

interface ErrorOptions {
  context?: string;
}

export function logAndNoticeError(
  error: Error | AxiosError,
  defaultMessage: string,
  options: ErrorOptions = {}
): void {
  const { context } = options;
  const errorContext = context ? `${defaultMessage} (${context})` : defaultMessage;
  logger.error(errorContext, error);

  const axiosError = error as AxiosError<{ msg?: string; error?: string }>;
  const errorMessage =
    axiosError?.response?.data?.msg ||
    axiosError?.response?.data?.error ||
    error?.message ||
    "未知错误";

  ElMessage.error(`${defaultMessage}: ${errorMessage}`);
}
