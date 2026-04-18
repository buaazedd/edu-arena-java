package com.edu.arena.dto.response;

import lombok.Data;

/**
 * 用户信息响应
 */
@Data
public class UserVO {

    private Long userId;
    private String username;
    private String displayName;
    private String role;

}
