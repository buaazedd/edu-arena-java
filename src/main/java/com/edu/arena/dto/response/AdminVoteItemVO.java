package com.edu.arena.dto.response;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 后台管理「投票记录」Tab 列表条目。
 *
 * <p>仅供 admin 使用，服务端不做脱敏；winner 展示为真实模型名（或"平局"）。</p>
 */
@Data
public class AdminVoteItemVO {

    private Long voteId;
    private Long battleId;

    /** 投票人 */
    private Long voterUserId;
    private String voterUsername;
    private String voterDisplayName;
    /** displayName 优先回退 username，由 Mapper 直接组装（MySQL COALESCE） */
    private String voter;

    /** 对战相关 */
    private String essayTitle;
    private String gradeLevel;
    private String modelA;
    private String modelB;

    /** 总体获胜方: A/B/tie */
    private String winner;
    /** 获胜模型名（winner=tie 时为"平局"） */
    private String winnerLabel;

    /** 六维度 A/B/tie */
    private String dimTheme;
    private String dimImagination;
    private String dimLogic;
    private String dimLanguage;
    private String dimWriting;
    private String dimOverall;

    /** 投票耗时（秒） */
    private Double voteTime;

    private LocalDateTime createdAt;
}
