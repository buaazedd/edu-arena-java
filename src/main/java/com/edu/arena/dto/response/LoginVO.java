package com.edu.arena.dto.response;

import lombok.Data;

/**
 * 登录响应
 */
@Data
public class LoginVO {

    private String token;
    private String role;
    private Long userId;
    private String displayName;

}
