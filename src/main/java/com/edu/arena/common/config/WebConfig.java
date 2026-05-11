package com.edu.arena.common.config;

import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Configuration;
import org.springframework.lang.NonNull;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * Web Configuration
 */
@Configuration
@RequiredArgsConstructor
public class WebConfig implements WebMvcConfigurer {

    private final AuthInterceptor authInterceptor;

    @Override
    public void configureAsyncSupport(@NonNull AsyncSupportConfigurer configurer) {
        // 异步请求超时：30 分钟。
        // 同时覆盖：
        //   1) SSE 长连接（聊天/对战流式输出）
        //   2) StreamingResponseBody（/api/admin/export/dataset.zip 导出 ZIP，
        //      含大批量 base64 图片解码 + 写盘，可能耗时较长）
        // 必须 >= @Transactional(timeout=1800) 与 HikariCP leak-detection-threshold(1800000)，
        // 否则会先抛 AsyncRequestTimeoutException 把连接强制关闭。
        configurer.setDefaultTimeout(1_800_000L);
    }

    @Override
    public void addCorsMappings(@NonNull CorsRegistry registry) {
        registry.addMapping("/**")
                .allowedOriginPatterns("*")
                .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
                .allowedHeaders("*")
                .allowCredentials(true)
                .maxAge(3600);
    }

    @Override
    @SuppressWarnings("null")
    public void addInterceptors(@NonNull InterceptorRegistry registry) {
        registry.addInterceptor(authInterceptor)
                .addPathPatterns("/**")
                .excludePathPatterns(
                        "/api/login",
                        "/api/register",
                        "/",
                        "/battle",
                        "/leaderboard",
                        "/history",
                        "/admin",
                        "/doc.html",
                        "/webjars/**",
                        "/swagger-resources/**",
                        "/v3/api-docs/**",
                        "/favicon.ico",
                        "/favicon.svg",
                        "/static/**"
                );
    }

}
