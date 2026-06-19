import type { AxiosError } from "axios";
import { logAndNoticeError } from "@/utils/error";
import { logger } from "@/utils/logger";

export interface ErrorHandlerOptions {
  showMessage?: boolean;
  logError?: boolean;
  context?: string;
  customMessage?: string;
}

export function useErrorHandler() {
  const handleError = (
    error: unknown,
    defaultMessage: string,
    options: ErrorHandlerOptions = {}
  ): void => {
    const { showMessage = true, logError = true, context, customMessage } = options;
    const errorObj =
      error instanceof Error
        ? error
        : new Error(error !== null && error !== undefined ? String(error) : "未知错误");

    if (logError) {
      if (context) {
        logger.error(`[${context}] ${defaultMessage}`, errorObj);
      } else {
        logger.error(defaultMessage, errorObj);
      }
    }

    if (showMessage) {
      const message = customMessage || defaultMessage;
      logAndNoticeError(errorObj, message, { context });
    }
  };

  return {
    handleError,
  };
}
