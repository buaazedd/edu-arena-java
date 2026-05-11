package com.edu.arena.common.exception;

import com.edu.arena.common.result.Result;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.lang.NonNull;
import org.springframework.validation.BindException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * 全局异常处理
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    /**
     * 忽略Chrome DevTools等客户端自动请求的资源不存在错误
     */
    @ExceptionHandler(NoResourceFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Result<Void> handleNoResourceFoundException(@NonNull NoResourceFoundException e) {
        // 忽略.well-known等客户端自动请求，只记录debug日志
        if (e.getResourcePath() != null && e.getResourcePath().contains(".well-known")) {
            log.debug("客户端自动请求资源不存在: {}", e.getResourcePath());
        } else {
            log.warn("静态资源不存在: {}", e.getResourcePath());
        }
        return Result.error(404, "资源不存在");
    }

    @ExceptionHandler(BusinessException.class)
    public Result<Void> handleBusinessException(@NonNull BusinessException e) {
        log.warn("业务异常: {}", e.getMessage());
        return Result.error(e.getCode(), e.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Result<Void> handleValidationException(@NonNull MethodArgumentNotValidException e) {
        String message = e.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .findFirst()
                .orElse("参数验证失败");
        log.warn("参数验证失败: {}", message);
        return Result.error(400, message);
    }

    @ExceptionHandler(BindException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Result<Void> handleBindException(@NonNull BindException e) {
        String message = e.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField() + ": " + error.getDefaultMessage())
                .findFirst()
                .orElse("参数绑定失败");
        log.warn("参数绑定失败: {}", message);
        return Result.error(400, message);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Result<Void> handleHttpMessageNotReadable(@NonNull HttpMessageNotReadableException e) {
        // 客户端 body 残缺 / JSON 格式错误 / 连接提前关闭导致的 EOF
        // 应返回 400 让客户端自行修正，而不是 500 触发客户端 5xx 重试风暴
        log.warn("请求体解析失败: {}", e.getMostSpecificCause().getMessage());
        return Result.error(400, "请求体格式错误");
    }

    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public Result<Void> handleException(@NonNull Exception e) {
        log.error("系统异常", e);
        return Result.error("系统繁忙，请稍后重试");
    }

}
