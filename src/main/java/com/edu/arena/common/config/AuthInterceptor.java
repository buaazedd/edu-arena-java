package com.edu.arena.common.config;

import com.edu.arena.common.utils.JwtUtils;
import com.edu.arena.common.utils.UserContext;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.lang.NonNull;
import org.springframework.lang.Nullable;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * 认证拦截器
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AuthInterceptor implements HandlerInterceptor {

    private final JwtUtils jwtUtils;

    @Value("${edu-arena.auth-bypass-enabled:false}")
    private boolean authBypassEnabled;

    @Value("${edu-arena.auth-bypass-role:admin}")
    private String authBypassRole;

    @Value("${edu-arena.auth-bypass-user-id:0}")
    private Long authBypassUserId;

    @Value("${edu-arena.auth-bypass-username:local-dev}")
    private String authBypassUsername;

    @Override
    public boolean preHandle(@NonNull HttpServletRequest request, @NonNull HttpServletResponse response, @NonNull Object handler) throws Exception {
        // 放行OPTIONS请求
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }

        if (authBypassEnabled && isBypassRequest(request)) {
            UserContext.setUserId(authBypassUserId);
            UserContext.setUsername(authBypassUsername);
            UserContext.setRole(authBypassRole);
            log.debug("Auth bypass enabled for local development: path={}, role={}", request.getRequestURI(), authBypassRole);
            return true;
        }

        String token = request.getHeader("Authorization");
        if (token != null && token.startsWith("Bearer ")) {
            token = token.substring(7);
            if (jwtUtils.validateToken(token)) {
                UserContext.setUserId(jwtUtils.getUserId(token));
                UserContext.setUsername(jwtUtils.getUsername(token));
                UserContext.setRole(jwtUtils.getRole(token));
            }
        }
        return true;
    }

    private boolean isBypassRequest(HttpServletRequest request) {
        String path = request.getRequestURI();
        return path != null && path.startsWith("/api/admin/");
    }

    @Override
    public void afterCompletion(@NonNull HttpServletRequest request, @NonNull HttpServletResponse response, @NonNull Object handler, @Nullable Exception ex) throws Exception {
        UserContext.clear();
    }

}
