package com.edu.arena.service;

import com.edu.arena.dto.request.LoginRequest;
import com.edu.arena.dto.request.RegisterRequest;
import com.edu.arena.dto.response.LoginVO;
import com.edu.arena.dto.response.UserVO;

/**
 * 认证服务接口
 */
public interface AuthService {

    /**
     * 用户注册
     */
    void register(RegisterRequest request);

    /**
     * 用户登录
     */
    LoginVO login(LoginRequest request);

    /**
     * 获取当前用户信息
     */
    UserVO getCurrentUser();

    /**
     * 退出登录
     */
    void logout();

}
