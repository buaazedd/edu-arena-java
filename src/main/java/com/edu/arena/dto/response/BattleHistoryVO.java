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

}
