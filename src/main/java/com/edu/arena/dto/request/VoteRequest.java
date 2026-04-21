package com.edu.arena.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

/**
 * 投票请求
 */
@Data
public class VoteRequest {

    /**
     * 主旨维度投票: left, right, tie
     */
    @NotBlank(message = "请完成主旨维度投票")
    @Pattern(regexp = "^(left|right|tie)$", message = "主旨维度投票值无效")
    private String dimTheme;

    /**
     * 想象维度投票
     */
    @NotBlank(message = "请完成想象维度投票")
    @Pattern(regexp = "^(left|right|tie)$", message = "想象维度投票值无效")
    private String dimImagination;

    /**
     * 逻辑维度投票
     */
    @NotBlank(message = "请完成逻辑维度投票")
    @Pattern(regexp = "^(left|right|tie)$", message = "逻辑维度投票值无效")
    private String dimLogic;

    /**
     * 语言维度投票
     */
    @NotBlank(message = "请完成语言维度投票")
    @Pattern(regexp = "^(left|right|tie)$", message = "语言维度投票值无效")
    private String dimLanguage;

    /**
     * 书写维度投票
     */
    @NotBlank(message = "请完成书写维度投票")
    @Pattern(regexp = "^(left|right|tie)$", message = "书写维度投票值无效")
    private String dimWriting;

    /**
     * 整体评价维度投票（决定最终胜负）
     */
    @NotBlank(message = "请完成整体评价维度投票")
    @Pattern(regexp = "^(left|right|tie)$", message = "整体评价维度投票值无效")
    private String dimOverall;

    /**
     * 主旨维度评分理由
     */
    private String dimThemeReason;

    /**
     * 想象维度评分理由
     */
    private String dimImaginationReason;

    /**
     * 逻辑维度评分理由
     */
    private String dimLogicReason;

    /**
     * 语言维度评分理由
     */
    private String dimLanguageReason;

    /**
     * 书写维度评分理由
     */
    private String dimWritingReason;

    /**
     * 整体评价维度评分理由
     */
    private String dimOverallReason;

    /**
     * 投票耗时(秒)
     */
    private Double voteTime;

}
