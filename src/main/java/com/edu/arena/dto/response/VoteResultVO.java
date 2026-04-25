package com.edu.arena.dto.response;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.math.BigDecimal;

/**
 * 投票结果响应
 */
@Data
public class VoteResultVO {

    @JsonProperty("message")
    private String message;
    @JsonProperty("overall_winner")
    private String overallWinner;
    @JsonProperty("a_wins")
    private Integer aWins;
    @JsonProperty("b_wins")
    private Integer bWins;
    @JsonProperty("winner_side")
    private String winnerSide;
    @JsonProperty("winner_label")
    private String winnerLabel;
    @JsonProperty("left_model_slot")
    private String leftModelSlot;
    @JsonProperty("right_model_slot")
    private String rightModelSlot;
    @JsonProperty("elo_a_before")
    private BigDecimal eloABefore;
    @JsonProperty("elo_a_after")
    private BigDecimal eloAAfter;
    @JsonProperty("elo_b_before")
    private BigDecimal eloBBefore;
    @JsonProperty("elo_b_after")
    private BigDecimal eloBAfter;

    /** 当前投票人 id（即本次操作者） */
    @JsonProperty("voter_user_id")
    private Long voterUserId;
    /** 当前投票人展示名（displayName 优先，回退 username） */
    @JsonProperty("voter")
    private String voter;

}
