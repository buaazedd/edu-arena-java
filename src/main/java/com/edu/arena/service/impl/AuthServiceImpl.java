package com.edu.arena.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.edu.arena.common.cache.CacheService;
import com.edu.arena.common.exception.BusinessException;
import com.edu.arena.common.utils.JwtUtils;
import com.edu.arena.common.utils.UserContext;
import com.edu.arena.dto.request.LoginRequest;
import com.edu.arena.dto.request.RegisterRequest;
import com.edu.arena.dto.response.LoginVO;
import com.edu.arena.dto.response.UserVO;
import com.edu.arena.entity.User;
import com.edu.arena.mapper.UserMapper;
import com.edu.arena.service.AuthService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

/**
 * 认证服务实现
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AuthServiceImpl implements AuthService {

    private final UserMapper userMapper;
    private final BCryptPasswordEncoder passwordEncoder;
    private final JwtUtils jwtUtils;
    private final CacheService cacheService;

    @Override
    public void register(RegisterRequest request) {
        // 检查用户名是否已存在
        Long count = userMapper.selectCount(
                new LambdaQueryWrapper<User>().eq(User::getUsername, request.getUsername())
        );
        if (count > 0) {
            throw new BusinessException("用户名已存在");
        }

        // 创建用户
        User user = new User();
        user.setUsername(request.getUsername());
        user.setPassword(passwordEncoder.encode(request.getPassword()));
        user.setDisplayName(request.getDisplayName() != null ? request.getDisplayName() : request.getUsername());
        user.setRole("teacher");

        userMapper.insert(user);
        log.info("用户注册成功: {}", request.getUsername());
    }

    @Override
    public LoginVO login(LoginRequest request) {
        // 查找用户
        User user = userMapper.selectOne(
                new LambdaQueryWrapper<User>().eq(User::getUsername, request.getUsername())
        );

        if (user == null || !passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            throw new BusinessException("用户名或密码错误");
        }

        // 更新最后登录时间
        user.setLastLogin(LocalDateTime.now());
        userMapper.updateById(user);

        // 缓存用户信息
        cacheService.cacheUser(user.getId(), user);

        // 生成Token
        String token = jwtUtils.generateToken(user.getId(), user.getUsername(), user.getRole());

        LoginVO vo = new LoginVO();
        vo.setToken(token);
        vo.setRole(user.getRole());
        vo.setUserId(user.getId());
        vo.setDisplayName(user.getDisplayName());

        log.info("用户登录成功: {}", user.getUsername());
        return vo;
    }

    @Override
    public UserVO getCurrentUser() {
        Long userId = UserContext.getUserId();
        if (userId == null) {
            throw new BusinessException(401, "请先登录");
        }

        // 尝试从缓存获取用户信息
        User user = cacheService.getOrLoad(
                cacheService.getUserKey(userId),
                CacheService.TTL_LONG,
                () -> userMapper.selectById(userId)
        );

        if (user == null) {
            // 清除无效缓存
            cacheService.invalidateUser(userId);
            throw new BusinessException(401, "用户不存在");
        }

        UserVO vo = new UserVO();
        vo.setUserId(user.getId());
        vo.setUsername(user.getUsername());
        vo.setDisplayName(user.getDisplayName());
        vo.setRole(user.getRole());

        return vo;
    }

    @Override
    public void logout() {
        Long userId = UserContext.getUserId();
        // 清除用户缓存
        if (userId != null) {
            cacheService.invalidateUser(userId);
        }
        // JWT无状态，客户端清除Token即可
        log.info("用户退出登录: {}", UserContext.getUsername());
    }

}
