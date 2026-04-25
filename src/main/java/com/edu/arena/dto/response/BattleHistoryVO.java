package com.edu.arena.dto.response;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 对战历史项
 * 注：字段命名使用camelCase，Jackson配置SNAKE_CASE策略后会自动转换为snake_case
 */
@Data
public class BattleHistoryVO {

    private Long id;
    private String essayTitle;
    private String gradeLevel;
    private String modelA;
    private String modelB;
    private String winner;
    private String matchType;
    private LocalDateTime createdAt;

    /** 投票人 id（原始值，SQL 直接返回；控制器脱敏后再决定是否暴露） */
    private Long voterUserId;
    /** 投票人 username（原始值，SQL 直接返回） */
    private String voterUsername;
    /** 投票人 displayName（原始值，SQL 直接返回） */
    private String voterDisplayName;
    /** 展示用：displayName 优先回退 username 或 "匿名"，由控制器按角色填充 */
    private String voter;

}
