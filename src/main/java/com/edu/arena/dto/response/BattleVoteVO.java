package com.edu.arena.dto.response;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 对战详情中的投票明细（BattleVO.vote）
 *
 * <p>service 层填充原始投票人字段（voterUserId/voterUsername/voterDisplayName），
 * controller 层根据当前用户角色进行脱敏后写入 voter 字段。</p>
 *
 * <p>维度值与 {@code votes} 表保持一致：{@code A/B/tie}。</p>
 */
@Data
public class BattleVoteVO {

    private Long voteId;

    /** 总体获胜方: A/B/tie */
    private String winner;

    private String dimTheme;
    private String dimImagination;
    private String dimLogic;
    private String dimLanguage;
    private String dimWriting;
    private String dimOverall;

    private String dimThemeReason;
    private String dimImaginationReason;
    private String dimLogicReason;
    private String dimLanguageReason;
    private String dimWritingReason;
    private String dimOverallReason;

    /** 原始投票人信息（服务层填充，控制器脱敏时参考） */
    private Long voterUserId;
    private String voterUsername;
    private String voterDisplayName;

    /** 展示用：控制器层根据当前用户角色脱敏后填充。displayName 优先，回退 username，或 "匿名"。 */
    private String voter;

    private LocalDateTime createdAt;
}
